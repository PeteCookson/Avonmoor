"""Atomic mileage workflow. No bank transaction or fuel expense is created here."""
from calendar import monthrange
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from .models import MileageLedger, MileageJourney, MileageClaim, MileageClaimLine, Expense


def tax_year(day):
    return day.year - (day < date(day.year, 4, 6))


def allocation(day, miles, cumulative):
    year = tax_year(day)
    rate = Decimal('0.55') if year >= 2026 else Decimal('0.45')
    higher = min(miles, max(Decimal('0'), Decimal('10000') - cumulative))
    lower = miles - higher
    return dict(tax_year=year, cumulative_before=cumulative, miles=miles,
                higher_rate_miles=higher, higher_rate=rate, lower_rate_miles=lower,
                amount=(higher * rate + lower * Decimal('0.25')).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))


def staff(user, owner=False):
    if not user.is_active or not user.is_staff or (owner and not user.is_superuser):
        raise PermissionDenied


def ledger_lock():
    return MileageLedger.objects.select_for_update().get(pk=1)


def frozen_after(journey):
    """Reject changes that could change a finalized claim's chronological rate."""
    year = tax_year(journey.journey_date)
    return MileageClaimLine.objects.filter(
        active=True, claim__status__in=['approved', 'paid'], tax_year=year,
    ).filter(Q(journey__journey_date__gt=journey.journey_date) |
             Q(journey__journey_date=journey.journey_date, journey_id__gte=journey.pk)).exists()


def allocations():
    totals = {}
    result = {}
    for journey in MileageJourney.objects.filter(status='approved').order_by('journey_date', 'pk'):
        year = tax_year(journey.journey_date)
        before = totals.get(year, Decimal('0'))
        result[journey.pk] = allocation(journey.journey_date, journey.total_miles, before)
        totals[year] = before + journey.total_miles
    return result


@transaction.atomic
def review_journey(pk, user, void=False):
    staff(user, owner=void)
    ledger_lock()
    journey = MileageJourney.objects.select_for_update().get(pk=pk)
    if journey.status == 'void' or journey.claim_lines.filter(active=True).exists():
        raise ValidationError('This journey is void or reserved by a claim. Void the claim first.')
    if not void and journey.status != 'draft':
        raise ValidationError('This journey has already been approved.')
    if frozen_after(journey):
        raise ValidationError('A later claim in this tax year is finalized. Review and void affected claims in reverse date order before changing earlier mileage.')
    if not void and not journey.is_complete:
        raise ValidationError('Add the end odometer reading before approving this day.')
    if not void and journey.is_daily:
        if not journey.route_description and not journey.stops.exists():
            raise ValidationError('Select properties visited or add a short route description before approving this day.')
        journey.stops_snapshot = [dict(id=stop.pk, label=f'{stop.customer.display_name} — {stop}') for stop in journey.stops.select_related('customer').all()]
    journey.full_clean()
    if void:
        journey.status, journey.voided_by, journey.voided_at = 'void', user, timezone.now()
    else:
        journey.status, journey.reviewed_by, journey.reviewed_at = 'approved', user, timezone.now()
    journey.save()
    return journey


@transaction.atomic
def generate_claim(month, branch, user):
    staff(user)
    ledger = ledger_lock()
    month = month.replace(day=1)
    claim, _ = MileageClaim.objects.get_or_create(
        ledger=ledger, month=month, branch=branch, status='draft', defaults={'created_by': user})
    end = date(month.year, month.month, monthrange(month.year, month.month)[1])
    reserved = MileageClaimLine.objects.filter(active=True).values('journey_id')
    journeys = list(MileageJourney.objects.filter(status='approved', branch=branch,
                    journey_date__range=(month, end)).exclude(pk__in=reserved))
    rates = allocations()
    for journey in journeys:
        MileageClaimLine.objects.create(claim=claim, journey=journey, **rates[journey.pk])
    if not claim.lines.exists():
        raise ValidationError('No approved, unclaimed journeys in this branch and month.')
    refresh_claim(claim, rates)
    return claim


def refresh_claim(claim, rates=None):
    rates = allocations() if rates is None else rates
    total = Decimal('0')
    for line in claim.lines.select_related('journey'):
        if line.journey.status != 'approved' or line.journey.branch != claim.branch or line.journey.journey_date.replace(day=1) != claim.month:
            raise ValidationError('Claim evidence no longer matches its journeys.')
        for key, value in rates[line.journey_id].items():
            setattr(line, key, value)
        line.save()
        total += line.amount
    claim.total = total
    claim.save(update_fields=['total'])


@transaction.atomic
def transition_claim(pk, action, user, reference=''):
    staff(user, owner=True)
    ledger_lock()
    claim = MileageClaim.objects.select_for_update().get(pk=pk)
    now = timezone.now()
    if action == 'approve' and claim.status == 'draft':
        if not claim.lines.filter(active=True).exists():
            raise ValidationError('Empty claims cannot be approved.')
        refresh_claim(claim)
        if claim.total <= 0:
            raise ValidationError('The claim must have a positive reimbursement amount.')
        claim.expense = Expense.objects.create(
            branch=claim.branch, expense_date=date(claim.month.year, claim.month.month, monthrange(claim.month.year, claim.month.month)[1]),
            supplier='Pete Cookson', category=Expense.Category.MILEAGE,
            description=f'{claim.number}: personal Ford Transit Connect business mileage',
            amount=claim.total, payment_method=Expense.PaymentMethod.BANK,
            reference=claim.number, notes='Owner-approved mileage reimbursement. Payment pending; see mileage claim.', created_by=user)
        claim.status, claim.approved_by, claim.approved_at = 'approved', user, now
    elif action == 'paid' and claim.status == 'approved':
        if not reference.strip():
            raise ValidationError('Enter the reimbursement bank payment reference.')
        claim.status, claim.paid_by, claim.paid_at = 'paid', user, now
        claim.payment_reference = reference.strip()
        claim.expense.notes = f'Owner-approved mileage reimbursement. Paid {timezone.localdate(now)}; bank reference: {claim.payment_reference}'
        claim.expense.updated_by = user
        claim.expense.save(update_fields=['notes', 'updated_by', 'updated_at'])
    elif action == 'void' and claim.status in ['draft', 'approved']:
        if not reference.strip():
            raise ValidationError('Enter a reason for voiding this claim.')
        # All journeys remain approved: voiding a claim does not change cumulative miles.
        if claim.expense_id:
            claim.expense.void(user)
        claim.lines.update(active=False)
        claim.status, claim.voided_by, claim.voided_at = 'void', user, now
        claim.void_reason = reference.strip()
    else:
        raise ValidationError('Invalid status transition. Paid claims are locked; retain payment evidence.')
    claim.save()
    return claim
