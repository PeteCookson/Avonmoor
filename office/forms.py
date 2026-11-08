from django import forms
from django.db.models import Q
from django.forms import inlineformset_factory

from .models import (
    BusinessBranch,
    Customer,
    Expense,
    Invoice,
    InvoiceLine,
    Property,
    WorkEntry,
)
from .banking import (
    expense_suggestion,
    invoice_outstanding_minor,
    is_fuel_transaction,
)


class DateInput(forms.DateInput):
    input_type = 'date'


class CustomerPropertySelect(forms.Select):
    """Expose property ownership so the invoice UI can filter safely."""

    def create_option(self, name, value, label, selected, index, **kwargs):
        option = super().create_option(
            name, value, label, selected, index, **kwargs
        )
        instance = getattr(value, 'instance', None)
        if instance is not None:
            option['attrs']['data-customer-id'] = instance.customer_id
        return option


class WorkEntryCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    """Expose work ownership for customer/property filtering in the browser."""

    def create_option(self, name, value, label, selected, index, **kwargs):
        option = super().create_option(
            name, value, label, selected, index, **kwargs
        )
        instance = getattr(value, 'instance', None)
        if instance is not None:
            option['attrs']['data-customer-id'] = instance.property.customer_id
            option['attrs']['data-property-id'] = instance.property_id
        return option


def configure_invoice_choices(form, branch):
    """Limit bound choices and annotate unbound choices for client filtering."""

    current_property_id = getattr(form.instance, 'property_id', None)
    properties = Property.objects.filter(
        active=True, customer__branch=branch
    )
    if current_property_id:
        properties = Property.objects.filter(
            Q(active=True) | Q(pk=current_property_id),
            customer__branch=branch,
        )
    properties = properties.select_related('customer')
    work_entries = WorkEntry.objects.filter(
        invoice_line__isnull=True,
        property__customer__branch=branch,
    ).select_related('property', 'property__customer')

    if form.is_bound:
        customer_id = form.data.get(form.add_prefix('customer'))
        property_id = form.data.get(form.add_prefix('property'))
        if customer_id:
            properties = properties.filter(customer_id=customer_id)
            work_entries = work_entries.filter(
                property__customer_id=customer_id
            )
            if property_id:
                work_entries = work_entries.filter(property_id=property_id)
        else:
            properties = properties.none()
            work_entries = work_entries.none()

    form.fields['property'].queryset = properties
    form.fields['work_entries'].queryset = work_entries


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = [
            'display_name',
            'contact_name',
            'email',
            'phone',
            'billing_address_1',
            'billing_address_2',
            'town',
            'county',
            'postcode',
            'notes',
            'active',
        ]
        widgets = {'notes': forms.Textarea(attrs={'rows': 3})}


class PropertyForm(forms.ModelForm):
    same_as_billing = forms.BooleanField(
        required=False,
        label='Same as billing address',
        help_text='Use the customer billing address for this property.',
    )

    class Meta:
        model = Property
        fields = [
            'name',
            'address_line_1',
            'address_line_2',
            'town',
            'county',
            'postcode',
            'active',
        ]

    def __init__(self, *args, customer=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.customer = customer or getattr(self.instance, 'customer', None)
        for field_name in ('address_line_1', 'address_line_2', 'town', 'county', 'postcode'):
            self.fields[field_name].required = False
        if self.instance.pk and self.customer:
            same = all(
                getattr(self.instance, property_field) == getattr(self.customer, billing_field)
                for property_field, billing_field in (
                    ('address_line_1', 'billing_address_1'),
                    ('address_line_2', 'billing_address_2'),
                    ('town', 'town'),
                    ('county', 'county'),
                    ('postcode', 'postcode'),
                )
            )
            self.initial['same_as_billing'] = same

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('same_as_billing'):
            if not self.customer:
                raise forms.ValidationError('A customer is required to copy the billing address.')
            cleaned.update(
                address_line_1=self.customer.billing_address_1,
                address_line_2=self.customer.billing_address_2,
                town=self.customer.town,
                county=self.customer.county,
                postcode=self.customer.postcode,
            )
        else:
            for field_name in ('address_line_1', 'postcode'):
                if not cleaned.get(field_name):
                    self.add_error(field_name, 'This field is required.')
        return cleaned


class WorkEntryForm(forms.ModelForm):
    class Meta:
        model = WorkEntry
        fields = [
            'property',
            'service_date',
            'category',
            'description',
            'quantity',
            'unit',
            'unit_price',
        ]
        widgets = {'service_date': DateInput()}

    def __init__(self, *args, branch=BusinessBranch.GARDEN, **kwargs):
        super().__init__(*args, **kwargs)
        current_property_id = getattr(self.instance, 'property_id', None)
        properties = Property.objects.filter(
            active=True, customer__branch=branch
        )
        if current_property_id:
            properties = Property.objects.filter(
                Q(active=True) | Q(pk=current_property_id),
                customer__branch=branch,
            )
        self.fields['property'].queryset = properties.select_related('customer')


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = [
            'expense_date',
            'supplier',
            'category',
            'description',
            'property',
            'amount',
            'payment_method',
            'reference',
            'notes',
        ]
        widgets = {
            'expense_date': DateInput(),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }
        help_texts = {
            'property': 'Optional: link the cost to a specific customer property or job.',
            'amount': 'Enter the full amount paid.',
            'reference': 'Optional receipt, order or bank reference.',
        }

    def __init__(self, *args, branch=BusinessBranch.GARDEN, **kwargs):
        super().__init__(*args, **kwargs)
        self.branch = branch
        self.fields['category'].choices = [(value, label) for value, label in Expense.Category.choices if value not in [Expense.Category.MILEAGE, Expense.Category.FUEL]]
        current_property_id = getattr(self.instance, 'property_id', None)
        properties = Property.objects.filter(
            active=True, customer__branch=branch
        )
        if current_property_id:
            properties = Property.objects.filter(
                Q(active=True) | Q(pk=current_property_id),
                customer__branch=branch,
            )
        self.fields['property'].queryset = properties.select_related('customer')

    def clean(self):
        cleaned = super().clean()
        property_record = cleaned.get('property')
        if property_record and property_record.customer.branch != self.branch:
            self.add_error('property', 'Select a property from this branch.')
        return cleaned


class BankExpenseReviewForm(forms.Form):
    branch = forms.ChoiceField(
        choices=[('', 'Choose a business branch'), *BusinessBranch.choices]
    )
    supplier = forms.CharField(max_length=160)
    category = forms.ChoiceField(choices=Expense.Category.choices)
    description = forms.CharField(max_length=300)
    property = forms.ModelChoiceField(
        queryset=Property.objects.none(), required=False
    )
    reference = forms.CharField(max_length=160, required=False)
    notes = forms.CharField(
        required=False, widget=forms.Textarea(attrs={'rows': 3})
    )
    remember_supplier = forms.BooleanField(
        required=False,
        label='Remember this supplier for future payments',
        help_text=(
            'Future matching Monzo payments will be pre-filled with this '
            'branch, supplier, category and description.'
        ),
    )

    def __init__(self, *args, bank_transaction=None, **kwargs):
        self.bank_transaction = bank_transaction
        if bank_transaction and not args and 'initial' not in kwargs:
            suggestion = expense_suggestion(bank_transaction)
            kwargs['initial'] = {
                key: value
                for key, value in suggestion.items()
                if key != 'rule'
            }
        super().__init__(*args, **kwargs)
        self.fields['category'].choices = [(value, label) for value, label in Expense.Category.choices if value not in [Expense.Category.MILEAGE, Expense.Category.FUEL]]
        self.fields['property'].queryset = Property.objects.filter(
            active=True
        ).select_related('customer')

    def clean(self):
        cleaned = super().clean()
        if not self.bank_transaction or not self.bank_transaction.is_outgoing:
            raise forms.ValidationError('Select an outgoing GBP transaction.')
        if is_fuel_transaction(self.bank_transaction):
            raise forms.ValidationError(
                'Fuel is excluded because the van is personally owned.'
            )
        # Reimbursement settles the existing mileage expense; it is not a second cost.
        from .models import MileageClaim
        reference = (self.bank_transaction.reference or '').strip().casefold()
        bank_id = self.bank_transaction.external_id.casefold()
        text = f'{self.bank_transaction.description} {reference}'.casefold()
        for claim in MileageClaim.objects.filter(status__in=['approved', 'paid']):
            payment_ref = claim.payment_reference.strip().casefold()
            if claim.number.casefold() in text or (payment_ref and payment_ref in [reference, bank_id]):
                raise forms.ValidationError('This payment reimburses an existing mileage claim. Mark it paid through Mileage; do not create another expense.')
        property_record = cleaned.get('property')
        branch = cleaned.get('branch')
        if property_record and property_record.customer.branch != branch:
            self.add_error('property', 'Select a property from the chosen branch.')
        return cleaned


class InvoiceCreateForm(forms.ModelForm):
    work_entries = forms.ModelMultipleChoiceField(
        queryset=WorkEntry.objects.none(),
        required=False,
        widget=WorkEntryCheckboxSelectMultiple,
        help_text='Optional: include any completed, uninvoiced work now.',
    )

    class Meta:
        model = Invoice
        fields = ['customer', 'property', 'issue_date']
        widgets = {
            'property': CustomerPropertySelect(),
            'issue_date': DateInput(),
        }

    def __init__(self, *args, branch=BusinessBranch.GARDEN, **kwargs):
        super().__init__(*args, **kwargs)
        self.branch = branch
        self.fields['customer'].queryset = Customer.objects.filter(
            active=True, branch=branch
        )
        configure_invoice_choices(self, branch)

    def clean(self):
        cleaned = super().clean()
        customer = cleaned.get('customer')
        property_record = cleaned.get('property')
        work_entries = cleaned.get('work_entries')
        if customer and customer.branch != self.branch:
            self.add_error('customer', 'Select a customer from this branch.')
        if property_record and customer and property_record.customer_id != customer.id:
            self.add_error('property', 'Select a property belonging to this customer.')
        if work_entries and customer:
            invalid = [
                entry for entry in work_entries
                if entry.property.customer_id != customer.id
                or (property_record and entry.property_id != property_record.id)
            ]
            if invalid:
                self.add_error(
                    'work_entries',
                    'Every selected work entry must belong to this customer and property.',
                )
        return cleaned


class InvoiceForm(forms.ModelForm):
    work_entries = forms.ModelMultipleChoiceField(
        queryset=WorkEntry.objects.none(),
        required=False,
        label='Add completed work',
        widget=WorkEntryCheckboxSelectMultiple,
        help_text='Optional: add completed, uninvoiced work to this draft.',
    )

    class Meta:
        model = Invoice
        fields = ['customer', 'property', 'issue_date']
        widgets = {
            'property': CustomerPropertySelect(),
            'issue_date': DateInput(),
        }

    def __init__(self, *args, branch=None, **kwargs):
        super().__init__(*args, **kwargs)
        branch = branch or getattr(
            self.instance, 'branch', BusinessBranch.GARDEN
        )
        self.branch = branch
        current_customer_id = getattr(self.instance, 'customer_id', None)
        customers = Customer.objects.filter(active=True, branch=branch)
        if current_customer_id:
            customers = Customer.objects.filter(
                Q(active=True) | Q(pk=current_customer_id), branch=branch
            )
        self.fields['customer'].queryset = customers
        configure_invoice_choices(self, branch)

    def clean(self):
        cleaned = super().clean()
        customer = cleaned.get('customer')
        property_record = cleaned.get('property')
        work_entries = cleaned.get('work_entries')
        if customer and customer.branch != self.branch:
            self.add_error('customer', 'Select a customer from this branch.')
        if property_record and customer and property_record.customer_id != customer.id:
            self.add_error('property', 'Select a property belonging to this customer.')
        if work_entries and customer:
            invalid = [
                entry for entry in work_entries
                if entry.property.customer_id != customer.id
                or (property_record and entry.property_id != property_record.id)
            ]
            if invalid:
                self.add_error(
                    'work_entries',
                    'Every selected work entry must belong to this customer and property.',
                )
        return cleaned


class InvoiceEmailForm(forms.Form):
    recipient = forms.EmailField(label='Send to')
    subject = forms.CharField(max_length=255)
    message = forms.CharField(widget=forms.Textarea(attrs={'rows': 8}))


class BankCSVImportForm(forms.Form):
    csv_file = forms.FileField(
        label='Bank transactions CSV',
        help_text='Monzo CSV exports are supported. Maximum file size: 2 MB.',
        widget=forms.ClearableFileInput(attrs={'accept': '.csv,text/csv'}),
    )

    def clean_csv_file(self):
        uploaded_file = self.cleaned_data['csv_file']
        if not uploaded_file.name.lower().endswith('.csv'):
            raise forms.ValidationError('Select a CSV file.')
        if uploaded_file.size > 2 * 1024 * 1024:
            raise forms.ValidationError('The CSV file must be smaller than 2 MB.')
        return uploaded_file


class MonzoAccountForm(forms.Form):
    account = forms.ChoiceField(label='Avonmoor bank account')

    def __init__(self, *args, accounts=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.accounts = accounts or []
        self.fields['account'].choices = [
            (account['id'], account.get('description') or account['id'])
            for account in self.accounts
        ]

    def selected_account(self):
        account_id = self.cleaned_data['account']
        return next(
            account for account in self.accounts if account['id'] == account_id
        )


class PaymentMatchForm(forms.Form):
    invoice = forms.ModelChoiceField(
        queryset=Invoice.objects.none(),
        empty_label='Select an invoice',
    )

    def __init__(self, *args, bank_transaction=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.bank_transaction = bank_transaction
        if bank_transaction and bank_transaction.is_incoming:
            candidates = []
            invoices = Invoice.objects.filter(
                status__in=(Invoice.Status.ISSUED, Invoice.Status.PAID)
            ).select_related('customer').prefetch_related(
                'lines', 'payment_matches__transaction'
            )
            for invoice in invoices:
                if invoice_outstanding_minor(invoice) == bank_transaction.amount_minor:
                    candidates.append(invoice.pk)
            self.fields['invoice'].queryset = Invoice.objects.filter(
                pk__in=candidates
            ).select_related('customer')
            self.fields['invoice'].label_from_instance = self.invoice_label

    @staticmethod
    def invoice_label(invoice):
        return (
            f'{invoice.number} — {invoice.customer.display_name} — '
            f'£{invoice.total:.2f} ({invoice.get_branch_display()})'
        )


class InvoiceLineForm(forms.ModelForm):
    class Meta:
        model = InvoiceLine
        fields = [
            'service_date',
            'category',
            'description',
            'quantity',
            'unit',
            'unit_price',
            'sort_order',
        ]
        widgets = {
            'service_date': DateInput(),
            'description': forms.TextInput(),
            'sort_order': forms.HiddenInput(),
        }

    def has_changed(self):
        """Ignore the spare line until the user enters billable content."""

        if self.is_bound and not any(
            self.data.get(self.add_prefix(field_name))
            for field_name in ('description', 'quantity', 'unit_price')
        ):
            return False
        return super().has_changed()


InvoiceLineFormSet = inlineformset_factory(
    Invoice,
    InvoiceLine,
    form=InvoiceLineForm,
    extra=1,
    can_delete=True,
)
