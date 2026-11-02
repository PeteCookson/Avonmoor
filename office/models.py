from decimal import Decimal
from builtins import property as builtin_property

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone


class Customer(models.Model):
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


class InvoiceSequence(models.Model):
    year = models.PositiveSmallIntegerField(unique=True)
    last_number = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f'{self.year}: {self.last_number}'


class Invoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        ISSUED = 'issued', 'Issued'
        PAID = 'paid', 'Paid'
        CANCELLED = 'cancelled', 'Cancelled'

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
                year=invoice.issue_date.year
            )
            sequence.last_number += 1
            sequence.save(update_fields=['last_number'])
            invoice.number = (
                f'INV-{invoice.issue_date.year}-{sequence.last_number:03d}'
            )
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
