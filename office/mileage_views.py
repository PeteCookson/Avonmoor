import csv
from datetime import date
from decimal import Decimal
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from .views import BranchContextMixin, OfficeAccessMixin
from .models import MileageJourney, MileageClaim, MileageClaimLine
from .mileage_forms import MileageJourneyForm, DailyMileageForm
from .mileage import ledger_lock, review_journey, generate_claim, transition_claim, allocations, tax_year


def safe_cell(value):
    value = str(value) if value is not None else ''
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value


class MileageListView(BranchContextMixin, OfficeAccessMixin, View):
    def get(self, request, branch):
        journeys = MileageJourney.objects.filter(branch=branch).select_related('customer', 'property', 'work_entry').prefetch_related('claim_lines__claim').order_by('-journey_date', '-pk')
        rates = allocations()
        for journey in journeys:
            journey.estimate = rates.get(journey.pk)
            journey.reservation = next((line.claim for line in journey.claim_lines.all() if line.active), None)
        claims = MileageClaim.objects.filter(branch=branch)
        draft_claims = list(claims.filter(status='draft').prefetch_related('lines'))
        for claim in draft_claims:
            claim.total = sum((rates[line.journey_id]['amount'] for line in claim.lines.all()), Decimal('0'))
        display_claims = sorted(draft_claims + list(claims.exclude(status='draft')), key=lambda claim: (claim.month, claim.pk), reverse=True)
        year = tax_year(timezone.localdate())
        year_miles = sum((j.total_miles for j in journeys if j.status == 'approved' and tax_year(j.journey_date) == year), Decimal('0'))
        return render(request, 'office/mileage_list.html', self.branch_context(
            journeys=journeys, claims=display_claims, month=timezone.localdate().strftime('%Y-%m'), tax_year=year,
            year_miles=year_miles, owed=claims.filter(status='approved').aggregate(t=Sum('total'))['t'] or 0,
            paid=claims.filter(status='paid').aggregate(t=Sum('total'))['t'] or 0))


class MileageEntryView(BranchContextMixin, OfficeAccessMixin, View):
    def handle(self, request, branch, pk=None, daily=False):
        with transaction.atomic():
            ledger = ledger_lock()
            instance = get_object_or_404(MileageJourney, pk=pk, branch=branch, status='draft') if pk else MileageJourney(ledger=ledger, created_by=request.user, branch=branch)
            daily = instance.is_daily or daily
            if daily and not pk and request.method == 'GET':
                existing = MileageJourney.objects.filter(ledger=ledger, is_daily=True, journey_date=timezone.localdate()).exclude(status='void').first()
                if existing:
                    return redirect('office:mileage-edit' if existing.status == 'draft' else 'office:mileage-list', **({'branch': existing.branch, 'pk': existing.pk} if existing.status == 'draft' else {'branch': existing.branch}))
            form_class = DailyMileageForm if daily else MileageJourneyForm
            form = form_class(request.POST or None, instance=instance, branch=branch)
            if request.method == 'POST' and form.is_valid():
                form.save()
                messages.success(request, 'Day saved. Add the end reading when finished.' if daily and not form.instance.is_complete else 'Mileage saved for review.')
                return redirect('office:mileage-list', branch=branch)
        return render(request, 'office/mileage_form.html', self.branch_context(form=form, daily=daily, page_title=('Daily mileage' if daily else 'Record mileage journey'), submit_label=('Save day' if daily else 'Save journey for review')))

    get = handle
    post = handle


class MileageReviewView(BranchContextMixin, OfficeAccessMixin, View):
    def post(self, request, branch, pk, action):
        get_object_or_404(MileageJourney, pk=pk, branch=branch)
        if action not in ['approve', 'void']:
            return HttpResponse(status=404)
        try:
            review_journey(pk, request.user, void=action == 'void')
            messages.success(request, 'Journey ' + ('approved.' if action == 'approve' else 'voided.'))
        except ValidationError as error:
            messages.error(request, ' '.join(error.messages))
        return redirect('office:mileage-list', branch=branch)


class MileageGenerateView(BranchContextMixin, OfficeAccessMixin, View):
    def post(self, request, branch):
        try:
            month = date.fromisoformat(request.POST.get('month', '') + '-01')
            claim = generate_claim(month, branch, request.user)
        except (ValueError, ValidationError) as error:
            messages.error(request, ' '.join(error.messages) if isinstance(error, ValidationError) else 'Select a valid claim month.')
            return redirect('office:mileage-list', branch=branch)
        return redirect('office:mileage-claim', branch=branch, pk=claim.pk)


class MileageClaimView(BranchContextMixin, OfficeAccessMixin, View):
    def get(self, request, branch, pk):
        claim = get_object_or_404(MileageClaim.objects.select_related('ledger', 'created_by', 'approved_by', 'paid_by', 'voided_by'), pk=pk, branch=branch)
        lines = list(claim.lines.select_related('journey__customer', 'journey__property', 'journey__work_entry'))
        # Preview current rates without changing records on a GET request.
        if claim.status == 'draft':
            rates = allocations()
            for line in lines:
                for key, value in rates[line.journey_id].items():
                    setattr(line, key, value)
            claim.total = sum((line.amount for line in lines), Decimal('0'))
        return render(request, 'office/mileage_claim.html', self.branch_context(claim=claim, lines=lines))

    def post(self, request, branch, pk):
        get_object_or_404(MileageClaim, pk=pk, branch=branch)
        try:
            transition_claim(pk, request.POST.get('action'), request.user, request.POST.get('reference', ''))
            messages.success(request, 'Mileage claim updated.')
        except ValidationError as error:
            messages.error(request, ' '.join(error.messages))
        return redirect('office:mileage-claim', branch=branch, pk=pk)


class MileageExportView(BranchContextMixin, OfficeAccessMixin, View):
    def get(self, request, branch):
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="avonmoor-{branch}-mileage.csv"'
        response.write('\ufeff')
        writer = csv.writer(response)
        writer.writerow(['Journey ID', 'Claimant', 'Vehicle', 'Ownership', 'Branch', 'Journey date', 'Tax year starts', 'Start', 'Destination', 'Business purpose', 'Entered miles', 'Return journey', 'Start odometer', 'Finish odometer', 'Business miles', 'Customer', 'Property', 'Work entry ID', 'Journey status', 'Recorded by', 'Recorded at', 'Reviewed by', 'Reviewed at', 'Journey voided by', 'Journey voided at', 'Claim', 'Claim month', 'Claim status', 'Active claim line', 'Cumulative miles before', 'Higher rate miles', 'Higher rate GBP', '25p miles', 'Amount GBP', 'Expense ID', 'Claim created by', 'Claim created at', 'Owner approved by', 'Owner approved at', 'Paid by', 'Paid at', 'Payment reference', 'Claim voided by', 'Claim voided at', 'Void reason', 'Entry type', 'Day complete', 'Private miles', 'Properties visited', 'Other stops / route'])
        rates = allocations()
        journeys = MileageJourney.objects.filter(branch=branch).select_related('ledger', 'customer', 'property', 'created_by', 'reviewed_by', 'voided_by').prefetch_related('claim_lines__claim__created_by', 'claim_lines__claim__approved_by', 'claim_lines__claim__paid_by', 'claim_lines__claim__voided_by')
        for j in journeys:
            for line in list(j.claim_lines.all()) or [None]:
                claim = line.claim if line else None
                rate = rates.get(j.pk, {}) if not line or claim.status == 'draft' else {field: getattr(line, field) for field in ['tax_year', 'cumulative_before', 'higher_rate_miles', 'higher_rate', 'lower_rate_miles', 'amount']}
                values = [j.pk, j.ledger.claimant, j.ledger.vehicle, 'Personal', j.get_branch_display(), j.journey_date, tax_year(j.journey_date), j.start, j.destination, j.purpose, j.miles, j.return_journey, j.odometer_start, j.odometer_finish, j.total_miles, j.customer or '', j.property or '', j.work_entry_id or '', j.status, j.created_by, j.created_at, j.reviewed_by or '', j.reviewed_at or '', j.voided_by or '', j.voided_at or '']
                values += [claim.number if claim else '', claim.month if claim else '', claim.status if claim else '', line.active if line else '']
                values += [rate.get(field, '') for field in ['cumulative_before', 'higher_rate_miles', 'higher_rate', 'lower_rate_miles', 'amount']]
                values += [claim.expense_id or '', claim.created_by, claim.created_at, claim.approved_by or '', claim.approved_at or '', claim.paid_by or '', claim.paid_at or '', claim.payment_reference, claim.voided_by or '', claim.voided_at or '', claim.void_reason] if claim else [''] * 11
                values += ['Daily' if j.is_daily else 'Journey', j.is_complete, j.private_miles, j.stops_display, j.route_description]
                writer.writerow([safe_cell(value) for value in values])
        return response
