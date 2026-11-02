from django import forms
from django.db.models import Q
from django.forms import inlineformset_factory

from .models import Customer, Invoice, InvoiceLine, Property, WorkEntry


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


def configure_invoice_choices(form):
    """Limit bound choices and annotate unbound choices for client filtering."""

    current_property_id = getattr(form.instance, 'property_id', None)
    properties = Property.objects.filter(active=True)
    if current_property_id:
        properties = Property.objects.filter(
            Q(active=True) | Q(pk=current_property_id)
        )
    properties = properties.select_related('customer')
    work_entries = WorkEntry.objects.filter(
        invoice_line__isnull=True
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customer'].queryset = Customer.objects.filter(active=True)
        configure_invoice_choices(self)

    def clean(self):
        cleaned = super().clean()
        customer = cleaned.get('customer')
        property_record = cleaned.get('property')
        work_entries = cleaned.get('work_entries')
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current_customer_id = getattr(self.instance, 'customer_id', None)
        customers = Customer.objects.filter(active=True)
        if current_customer_id:
            customers = Customer.objects.filter(
                Q(active=True) | Q(pk=current_customer_id)
            )
        self.fields['customer'].queryset = customers
        configure_invoice_choices(self)

    def clean(self):
        cleaned = super().clean()
        customer = cleaned.get('customer')
        property_record = cleaned.get('property')
        work_entries = cleaned.get('work_entries')
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
