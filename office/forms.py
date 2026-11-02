from django import forms
from django.forms import inlineformset_factory

from .models import Customer, Invoice, InvoiceLine, Property, WorkEntry


class DateInput(forms.DateInput):
    input_type = 'date'


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
        widget=forms.CheckboxSelectMultiple,
        help_text='Optional: include any completed, uninvoiced work now.',
    )

    class Meta:
        model = Invoice
        fields = ['customer', 'property', 'issue_date']
        widgets = {'issue_date': DateInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customer'].queryset = Customer.objects.filter(active=True)
        self.fields['property'].queryset = Property.objects.filter(
            active=True
        ).select_related('customer')
        self.fields['work_entries'].queryset = WorkEntry.objects.filter(
            invoice_line__isnull=True
        ).select_related('property', 'property__customer')

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
    class Meta:
        model = Invoice
        fields = ['customer', 'property', 'issue_date']
        widgets = {'issue_date': DateInput()}

    def clean(self):
        cleaned = super().clean()
        customer = cleaned.get('customer')
        property_record = cleaned.get('property')
        if property_record and customer and property_record.customer_id != customer.id:
            self.add_error('property', 'Select a property belonging to this customer.')
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


InvoiceLineFormSet = inlineformset_factory(
    Invoice,
    InvoiceLine,
    form=InvoiceLineForm,
    extra=1,
    can_delete=True,
)
