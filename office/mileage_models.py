"""Mileage evidence and reimbursement ledger for Pete's personally owned van."""
from decimal import Decimal
from builtins import property as builtin_property
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from .models import BusinessBranch, Customer, Property, WorkEntry, Expense


class MileageLedger(models.Model):
    """Single claimant row also serializes all ledger mutations on PostgreSQL."""
    claimant = models.CharField(max_length=160, default='Pete Cookson')
    vehicle = models.CharField(max_length=160, default='Personally owned 2004 Ford Transit Connect')


class MileageJourney(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Awaiting review'
        APPROVED = 'approved', 'Approved'
        VOID = 'void', 'Void'
    ledger = models.ForeignKey(MileageLedger, on_delete=models.PROTECT)
    journey_date = models.DateField(default=timezone.localdate, db_index=True)
    branch = models.CharField(max_length=12, choices=BusinessBranch.choices)
    start = models.CharField('Starting location', max_length=200)
    destination = models.CharField(max_length=200)
    purpose = models.CharField('Business purpose', max_length=300)
    miles = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    odometer_start = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    odometer_finish = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    return_journey = models.BooleanField(default=False, help_text='Double manually entered one-way miles. Odometer readings must cover the complete journey and are never doubled.')
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, null=True, blank=True)
    property = models.ForeignKey(Property, on_delete=models.PROTECT, null=True, blank=True)
    work_entry = models.ForeignKey(WorkEntry, on_delete=models.PROTECT, null=True, blank=True)
    is_daily = models.BooleanField(default=False)
    private_miles = models.DecimalField(max_digits=9, decimal_places=2, default=Decimal('0'))
    route_description = models.CharField(max_length=300, blank=True)
    stops = models.ManyToManyField(Property, through='MileageStop', related_name='mileage_days', blank=True)
    stops_snapshot = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+', null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+', null=True, blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['journey_date', 'pk']
        constraints = [
            models.CheckConstraint(check=models.Q(miles__gt=0), name='mileage_positive_miles'),
            models.CheckConstraint(check=models.Q(private_miles__gte=0), name='mileage_nonnegative_private'),
            models.UniqueConstraint(fields=['ledger', 'journey_date'], condition=models.Q(is_daily=True) & ~models.Q(status='void'), name='mileage_one_active_day'),
        ]

    def clean(self):
        errors = {}
        if self.journey_date and self.journey_date > timezone.localdate():
            errors['journey_date'] = 'Record completed journeys only.'
        if not self.is_daily and self.ledger_id and self.journey_date and MileageJourney.objects.filter(ledger_id=self.ledger_id, journey_date=self.journey_date, is_daily=True).exclude(status='void').exclude(pk=self.pk).exists():
            errors['journey_date'] = 'A daily mileage record already covers this date. Edit that record instead.'
        if self.is_daily:
            self.clean_daily(errors)
        elif (self.odometer_start is None) != (self.odometer_finish is None):
            errors['odometer_finish'] = 'Supply both odometer readings.'
        if not self.is_daily and self.odometer_start is not None and self.odometer_finish is not None:
            if self.odometer_start < 0 or self.odometer_finish <= self.odometer_start:
                errors['odometer_finish'] = 'Finish reading must exceed the non-negative start reading.'
            else:
                self.miles = self.odometer_finish - self.odometer_start
        elif not self.is_daily and (self.miles is None or self.miles <= 0):
            errors['miles'] = 'Enter positive one-way miles or both odometer readings.'
        if self.customer_id and self.customer.branch != self.branch:
            errors['customer'] = 'Select a customer from this branch.'
        if self.property_id:
            if self.property.customer.branch != self.branch:
                errors['property'] = 'Select a property from this branch.'
            if self.customer_id and self.property.customer_id != self.customer_id:
                errors['property'] = 'Property must belong to the selected customer.'
        if self.work_entry_id:
            prop = self.work_entry.property
            if prop.customer.branch != self.branch or (self.property_id and prop.pk != self.property_id) or (self.customer_id and prop.customer_id != self.customer_id):
                errors['work_entry'] = 'Work entry must match this branch, customer and property.'
        if errors:
            raise ValidationError(errors)

    def clean_daily(self, errors):
        if self.odometer_start is None or self.odometer_start < 0:
            errors['odometer_start'] = 'Enter a non-negative start odometer reading.'
        if self.private_miles is None or self.private_miles < 0:
            errors['private_miles'] = 'Private miles cannot be negative.'
        if self.odometer_finish is None:
            self.miles = None
            if self.status == self.Status.APPROVED:
                errors['odometer_finish'] = 'Finish the day before approving mileage.'
        elif self.odometer_start is not None and self.private_miles is not None:
            distance = self.odometer_finish - self.odometer_start
            if distance <= 0:
                errors['odometer_finish'] = 'End odometer must exceed the start reading.'
            elif self.private_miles >= distance:
                errors['private_miles'] = 'Private miles must be less than the day’s total distance.'
            else:
                self.miles = distance - self.private_miles

    @builtin_property
    def is_complete(self):
        return not self.is_daily or (self.odometer_finish is not None and self.miles is not None)

    @builtin_property
    def stops_display(self):
        if self.stops_snapshot:
            return '; '.join(stop['label'] for stop in self.stops_snapshot)
        return '; '.join(f'{stop.customer.display_name} — {stop}' for stop in self.stops.select_related('customer').all())

    @builtin_property
    def total_miles(self):
        if self.miles is None:
            return Decimal('0')
        if self.is_daily:
            return self.miles
        return self.miles * (2 if self.return_journey and self.odometer_start is None else 1)


class MileageClaim(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        APPROVED = 'approved', 'Approved'
        PAID = 'paid', 'Paid'
        VOID = 'void', 'Void'
    ledger = models.ForeignKey(MileageLedger, on_delete=models.PROTECT)
    branch = models.CharField(max_length=12, choices=BusinessBranch.choices)
    month = models.DateField(help_text='First day of claim month')
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    expense = models.OneToOneField(Expense, on_delete=models.PROTECT, null=True, blank=True, related_name='mileage_claim')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+', null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    paid_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+', null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_reference = models.CharField(max_length=160, blank=True)
    voided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+', null=True, blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ['-month', '-pk']
        constraints = [models.UniqueConstraint(fields=['ledger', 'branch', 'month'], condition=models.Q(status='draft'), name='mileage_one_draft_per_month_branch')]

    @builtin_property
    def number(self):
        return f'MILE-{self.month:%Y%m}-{self.branch.upper()}-{self.pk}'


class MileageClaimLine(models.Model):
    claim = models.ForeignKey(MileageClaim, on_delete=models.PROTECT, related_name='lines')
    journey = models.ForeignKey(MileageJourney, on_delete=models.PROTECT, related_name='claim_lines')
    active = models.BooleanField(default=True)
    tax_year = models.PositiveIntegerField()
    cumulative_before = models.DecimalField(max_digits=12, decimal_places=2)
    miles = models.DecimalField(max_digits=9, decimal_places=2)
    higher_rate_miles = models.DecimalField(max_digits=9, decimal_places=2)
    higher_rate = models.DecimalField(max_digits=4, decimal_places=2)
    lower_rate_miles = models.DecimalField(max_digits=9, decimal_places=2)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ['journey__journey_date', 'journey_id']
        constraints = [models.UniqueConstraint(fields=['journey'], condition=models.Q(active=True), name='mileage_journey_claimed_once')]


class MileageStop(models.Model):
    journey = models.ForeignKey(MileageJourney, on_delete=models.PROTECT)
    property = models.ForeignKey(Property, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['journey', 'property'], name='mileage_unique_stop')]
