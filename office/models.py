from decimal import Decimal
from builtins import property as builtin_property

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone


class BusinessBranch(models.TextChoices):
    GARDEN = 'garden', 'Garden & Property'
    RAINWATER = 'rainwater', 'Rainwater Harvesting'


class Customer(models.Model):
    branch = models.CharField(
        max_length=12,
        choices=BusinessBranch.choices,
        default=BusinessBranch.GARDEN,
        db_index=True,
    )
    display_name = models.CharField(max_length=160)
    contact_name = models.CharField(max_length=160, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    billing_address_1 = models.CharField(max_length=160)
    billing_address_2 = models.CharField(max_length=160, blank=True)
    town = models.CharField(max_length=100, blank=True)
    county = models.CharField(max_length=100, blank=True)
    postcode = models.CharField(max_length=12)
    notes = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_name']

    def __str__(self):
        return self.display_name

    @property
    def billing_address_lines(self):
        return [
            value
            for value in (
                self.billing_address_1,
                self.billing_address_2,
                self.town,
                self.county,
                self.postcode,
            )
            if value
        ]

    def snapshot(self):
        return {
            'display_name': self.display_name,
            'contact_name': self.contact_name,
            'email': self.email,
            'phone': self.phone,
            'billing_address_1': self.billing_address_1,
            'billing_address_2': self.billing_address_2,
            'town': self.town,
            'county': self.county,
            'postcode': self.postcode,
        }


class Property(models.Model):
    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, related_name='properties'
    )
    name = models.CharField(max_length=120, blank=True)
    address_line_1 = models.CharField(max_length=160)
    address_line_2 = models.CharField(max_length=160, blank=True)
    town = models.CharField(max_length=100, blank=True)
    county = models.CharField(max_length=100, blank=True)
    postcode = models.CharField(max_length=12)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['customer__display_name', 'address_line_1']
        verbose_name_plural = 'properties'

    def __str__(self):
        return self.name or ', '.join(
            value for value in (self.address_line_1, self.postcode) if value
        )

    @property
    def address_lines(self):
        return [
            value
            for value in (
                self.address_line_1,
                self.address_line_2,
                self.town,
                self.county,
                self.postcode,
            )
            if value
        ]

    def snapshot(self):
        return {
            'name': self.name,
            'address_line_1': self.address_line_1,
            'address_line_2': self.address_line_2,
            'town': self.town,
            'county': self.county,
            'postcode': self.postcode,
        }


class WorkEntry(models.Model):
    class Category(models.TextChoices):
        LABOUR = 'labour', 'Labour'
        MATERIALS = 'materials', 'Materials'
        WASTE = 'waste', 'Waste disposal'
        OTHER = 'other', 'Other'

    class Unit(models.TextChoices):
        HOURS = 'hours', 'hours'
        ITEMS = 'items', 'items'
        JOB = 'job', 'job'

    property = models.ForeignKey(
        Property, on_delete=models.PROTECT, related_name='work_entries'
    )
    service_date = models.DateField(default=timezone.localdate)
    category = models.CharField(
        max_length=20, choices=Category.choices, default=Category.LABOUR
    )
    description = models.CharField(max_length=300)
    quantity = models.DecimalField(
        max_digits=9, decimal_places=2, default=Decimal('1.00')
    )
    unit = models.CharField(
        max_length=12, choices=Unit.choices, default=Unit.HOURS
    )
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='office_work_entries',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-service_date', '-id']

    def __str__(self):
        return f'{self.service_date}: {self.description}'

    @builtin_property
    def total(self):
        return (self.quantity * self.unit_price).quantize(Decimal('0.01'))

    @builtin_property
    def is_invoiced(self):
        return hasattr(self, 'invoice_line')

    def clean(self):
        errors = {}
        if self.quantity is not None and self.quantity <= 0:
            errors['quantity'] = 'Quantity must be greater than zero.'
        if self.unit_price is not None and self.unit_price < 0:
            errors['unit_price'] = 'Unit price cannot be negative.'
        if self.pk and self.is_invoiced:
            errors['description'] = 'Invoiced work entries cannot be changed.'
        if errors:
            raise ValidationError(errors)


class Expense(models.Model):
    """An auditable business expense kept separate by trading branch."""

    class Category(models.TextChoices):
        MATERIALS = 'materials', 'Materials and supplies'
        TOOLS = 'tools', 'Tools and equipment'
        FUEL = 'fuel', 'Fuel and travel'
        MILEAGE = 'mileage', 'Personal vehicle mileage reimbursement'
        WASTE = 'waste', 'Waste disposal'
        SUBCONTRACTOR = 'subcontractor', 'Subcontractors'
        INSURANCE = 'insurance', 'Insurance and professional fees'
        OFFICE = 'office', 'Office and administration'
        OTHER = 'other', 'Other'

    class PaymentMethod(models.TextChoices):
        BANK = 'bank', 'Bank transfer'
        CARD = 'card', 'Business card'
        CASH = 'cash', 'Cash'
        OTHER = 'other', 'Other'

    branch = models.CharField(
        max_length=12,
        choices=BusinessBranch.choices,
        default=BusinessBranch.GARDEN,
        db_index=True,
    )
    expense_date = models.DateField(default=timezone.localdate, db_index=True)
    supplier = models.CharField(max_length=160)
    category = models.CharField(
        max_length=20, choices=Category.choices, default=Category.MATERIALS
    )
    description = models.CharField(max_length=300)
    property = models.ForeignKey(
        Property,
        on_delete=models.PROTECT,
        related_name='expenses',
        null=True,
        blank=True,
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(
        max_length=12,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CARD,
    )
    reference = models.CharField(max_length=160, blank=True)
    notes = models.TextField(blank=True)
    bank_transaction = models.OneToOneField(
        'BankTransaction',
        on_delete=models.PROTECT,
        related_name='expense_record',
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='office_expenses_created',
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='office_expenses_updated',
        null=True,
        blank=True,
    )
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='office_expenses_voided',
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-expense_date', '-id']

    def __str__(self):
        return f'{self.expense_date}: {self.supplier} ({self.amount})'

    @builtin_property
    def is_void(self):
        return self.voided_at is not None

    def clean(self):
        errors = {}
        if self.amount is not None and self.amount <= 0:
            errors['amount'] = 'Amount must be greater than zero.'
        if self.property_id and self.property.customer.branch != self.branch:
            errors['property'] = 'The property must belong to this expense branch.'
        if self.bank_transaction_id:
            if self.bank_transaction.amount_minor >= 0:
                errors['bank_transaction'] = 'An expense must use an outgoing transaction.'
            if self.amount != abs(self.bank_transaction.amount):
                errors['amount'] = 'The expense amount must match the bank transaction.'
        if errors:
            raise ValidationError(errors)

    def void(self, user):
        if self.voided_at:
            raise ValidationError('This expense is already void.')
        self.voided_at = timezone.now()
        self.voided_by = user
        self.save(update_fields=['voided_at', 'voided_by', 'updated_at'])


class InvoiceSequence(models.Model):
    branch = models.CharField(
        max_length=12,
        choices=BusinessBranch.choices,
        default=BusinessBranch.GARDEN,
    )
    year = models.PositiveSmallIntegerField()
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['branch', 'year'], name='office_invoice_sequence_branch_year'
            )
        ]

    def __str__(self):
        return f'{self.get_branch_display()} {self.year}: {self.last_number}'


class Invoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        ISSUED = 'issued', 'Issued'
        PAID = 'paid', 'Paid'
        CANCELLED = 'cancelled', 'Cancelled'

    branch = models.CharField(
        max_length=12,
        choices=BusinessBranch.choices,
        default=BusinessBranch.GARDEN,
        db_index=True,
    )
    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, related_name='invoices'
    )
    property = models.ForeignKey(
        Property,
        on_delete=models.PROTECT,
        related_name='invoices',
        null=True,
        blank=True,
    )
    number = models.CharField(max_length=24, unique=True, null=True, blank=True)
    issue_date = models.DateField(default=timezone.localdate)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.DRAFT
    )
    customer_snapshot = models.JSONField(default=dict, blank=True)
    property_snapshot = models.JSONField(default=dict, blank=True)
    issued_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='office_invoices',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-issue_date', '-id']

    def __str__(self):
        return self.number or f'Draft invoice {self.pk or "new"}'

    def clean(self):
        if self.customer_id and self.branch != self.customer.branch:
            raise ValidationError(
                {'customer': 'The customer must belong to this invoice branch.'}
            )
        if self.property_id and self.customer_id:
            if self.property.customer_id != self.customer_id:
                raise ValidationError(
                    {'property': 'The property must belong to the selected customer.'}
                )

    @builtin_property
    def total(self):
        return sum(
            (line.total for line in self.lines.all()), Decimal('0.00')
        ).quantize(Decimal('0.01'))

    @builtin_property
    def display_number(self):
        return self.number or f'DRAFT-{self.pk}'

    @builtin_property
    def billing_details(self):
        return self.customer_snapshot or self.customer.snapshot()

    @builtin_property
    def site_details(self):
        if self.property_snapshot:
            return self.property_snapshot
        return self.property.snapshot() if self.property_id else {}

    def issue(self):
        if self.status != self.Status.DRAFT:
            return self

        with transaction.atomic():
            invoice = Invoice.objects.select_for_update().get(pk=self.pk)
            if invoice.status != self.Status.DRAFT:
                return invoice
            if not invoice.lines.exists():
                raise ValidationError('Add at least one line before issuing the invoice.')
            if any(line.total < 0 for line in invoice.lines.all()):
                raise ValidationError('Invoice line totals cannot be negative.')

            sequence, _ = InvoiceSequence.objects.select_for_update().get_or_create(
                branch=invoice.branch,
                year=invoice.issue_date.year,
            )
            sequence.last_number += 1
            sequence.save(update_fields=['last_number'])
            prefix = (
                'GPM'
                if invoice.branch == BusinessBranch.GARDEN
                else 'RWH'
            )
            invoice.number = f'{prefix}-{invoice.issue_date:%Y%m%d}-{sequence.last_number:03d}'
            invoice.customer_snapshot = invoice.customer.snapshot()
            invoice.property_snapshot = (
                invoice.property.snapshot() if invoice.property_id else {}
            )
            invoice.status = self.Status.ISSUED
            invoice.issued_at = timezone.now()
            invoice.save(
                update_fields=[
                    'number',
                    'customer_snapshot',
                    'property_snapshot',
                    'status',
                    'issued_at',
                    'updated_at',
                ]
            )
        return invoice

    def mark_paid(self):
        if self.status != self.Status.ISSUED:
            raise ValidationError('Only issued invoices can be marked as paid.')
        self.status = self.Status.PAID
        self.paid_at = timezone.now()
        self.save(update_fields=['status', 'paid_at', 'updated_at'])

    def cancel(self):
        if self.status not in (self.Status.ISSUED, self.Status.PAID):
            raise ValidationError('Only issued or paid invoices can be cancelled.')
        self.status = self.Status.CANCELLED
        self.cancelled_at = timezone.now()
        self.save(update_fields=['status', 'cancelled_at', 'updated_at'])


class InvoiceLine(models.Model):
    invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE, related_name='lines'
    )
    work_entry = models.OneToOneField(
        WorkEntry,
        on_delete=models.PROTECT,
        related_name='invoice_line',
        null=True,
        blank=True,
    )
    service_date = models.DateField(default=timezone.localdate)
    category = models.CharField(
        max_length=20,
        choices=WorkEntry.Category.choices,
        default=WorkEntry.Category.LABOUR,
    )
    description = models.CharField(max_length=300)
    quantity = models.DecimalField(max_digits=9, decimal_places=2)
    unit = models.CharField(
        max_length=12, choices=WorkEntry.Unit.choices, default=WorkEntry.Unit.HOURS
    )
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'service_date', 'id']

    def __str__(self):
        return self.description

    @property
    def total(self):
        return (self.quantity * self.unit_price).quantize(Decimal('0.01'))

    def clean(self):
        errors = {}
        if self.quantity is not None and self.quantity <= 0:
            errors['quantity'] = 'Quantity must be greater than zero.'
        if self.unit_price is not None and self.unit_price < 0:
            errors['unit_price'] = 'Unit price cannot be negative.'
        if self.invoice_id and self.invoice.status != Invoice.Status.DRAFT:
            errors['description'] = 'Issued invoice lines cannot be changed.'
        if self.work_entry_id and self.invoice_id:
            if self.work_entry.property.customer.branch != self.invoice.branch:
                errors['work_entry'] = 'Work must belong to the invoice branch.'
            if self.work_entry.property.customer_id != self.invoice.customer_id:
                errors['work_entry'] = 'Work must belong to the invoice customer.'
            if (
                self.invoice.property_id
                and self.work_entry.property_id != self.invoice.property_id
            ):
                errors['work_entry'] = 'Work must belong to the invoice property.'
        if errors:
            raise ValidationError(errors)

    def delete(self, *args, **kwargs):
        if self.invoice.status != Invoice.Status.DRAFT:
            raise ValidationError('Issued invoice lines cannot be deleted.')
        return super().delete(*args, **kwargs)


class InvoiceEmail(models.Model):
    invoice = models.ForeignKey(
        Invoice, on_delete=models.PROTECT, related_name='email_history'
    )
    recipient = models.EmailField()
    subject = models.CharField(max_length=255)
    body = models.TextField()
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='office_invoice_emails',
    )
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-sent_at', '-id']

    def __str__(self):
        return f'{self.invoice.display_number} to {self.recipient}'


class BankConnection(models.Model):
    """One encrypted, read-only bank connection for Avonmoor Office."""

    provider = models.CharField(max_length=20, default='monzo', unique=True)
    account_id = models.CharField(max_length=80, blank=True)
    account_name = models.CharField(max_length=160, blank=True)
    access_token_encrypted = models.TextField(blank=True)
    refresh_token_encrypted = models.TextField(blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    webhook_id = models.CharField(max_length=80, blank=True)
    active = models.BooleanField(default=False)
    connected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='office_bank_connections',
    )
    last_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['provider']

    def __str__(self):
        return self.account_name or self.get_provider_display()

    def get_provider_display(self):
        return 'Monzo' if self.provider == 'monzo' else self.provider.title()

    def set_tokens(self, access_token, refresh_token=''):
        from .security import encrypt_secret

        self.access_token_encrypted = encrypt_secret(access_token)
        self.refresh_token_encrypted = (
            encrypt_secret(refresh_token) if refresh_token else ''
        )

    def access_token(self):
        from .security import decrypt_secret

        return decrypt_secret(self.access_token_encrypted)

    def refresh_token(self):
        from .security import decrypt_secret

        return decrypt_secret(self.refresh_token_encrypted)


class BankTransaction(models.Model):
    class Source(models.TextChoices):
        MONZO = 'monzo', 'Monzo'
        CSV = 'csv', 'CSV import'

    source = models.CharField(max_length=12, choices=Source.choices)
    external_id = models.CharField(max_length=180, unique=True)
    account_id = models.CharField(max_length=80, blank=True)
    amount_minor = models.BigIntegerField()
    currency = models.CharField(max_length=3, default='GBP')
    transaction_at = models.DateTimeField()
    settled_at = models.DateTimeField(null=True, blank=True)
    description = models.CharField(max_length=300, blank=True)
    reference = models.CharField(max_length=300, blank=True)
    raw_data = models.JSONField(default=dict, blank=True)
    ignored_at = models.DateTimeField(null=True, blank=True)
    ignored_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='office_ignored_bank_transactions',
    )
    imported_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-transaction_at', '-id']

    def __str__(self):
        return f'{self.transaction_at.date()}: {self.description} ({self.amount})'

    @builtin_property
    def amount(self):
        return (Decimal(self.amount_minor) / Decimal('100')).quantize(
            Decimal('0.01')
        )

    @builtin_property
    def is_incoming(self):
        return self.amount_minor > 0 and self.currency == 'GBP'

    @builtin_property
    def is_outgoing(self):
        return self.amount_minor < 0 and self.currency == 'GBP'

    @builtin_property
    def review_status(self):
        if hasattr(self, 'payment_match'):
            return 'matched'
        if self.ignored_at:
            return 'ignored'
        return 'review'


class ExpenseImportRule(models.Model):
    """Remember how a recurring Monzo supplier should be categorised."""

    match_text = models.CharField(max_length=160, unique=True)
    branch = models.CharField(max_length=12, choices=BusinessBranch.choices)
    supplier = models.CharField(max_length=160)
    category = models.CharField(max_length=20, choices=Expense.Category.choices)
    description = models.CharField(max_length=300)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='office_expense_import_rules_created',
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='office_expense_import_rules_updated',
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['supplier', 'match_text']

    def __str__(self):
        return f'{self.match_text} → {self.supplier}'


class PaymentMatch(models.Model):
    class Method(models.TextChoices):
        AUTOMATIC = 'automatic', 'Automatic'
        MANUAL = 'manual', 'Manual'

    transaction = models.OneToOneField(
        BankTransaction,
        on_delete=models.PROTECT,
        related_name='payment_match',
    )
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.PROTECT,
        related_name='payment_matches',
    )
    method = models.CharField(max_length=12, choices=Method.choices)
    matched_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='office_payment_matches',
    )
    matched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-matched_at', '-id']

    def __str__(self):
        return f'{self.transaction} → {self.invoice.display_number}'

# Imported after core models to keep mileage isolated without a second app.
from .mileage_models import MileageLedger, MileageJourney, MileageClaim, MileageClaimLine, MileageStop  # noqa: E402,F401
