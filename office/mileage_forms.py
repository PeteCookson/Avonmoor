from django import forms
from .forms import DateInput
from .models import MileageJourney, Customer, Property, WorkEntry


class MileageJourneyForm(forms.ModelForm):
    class Meta:
        model = MileageJourney
        fields = ['journey_date', 'start', 'destination', 'purpose', 'miles', 'odometer_start', 'odometer_finish', 'return_journey', 'customer', 'property', 'work_entry']
        widgets = {'journey_date': DateInput()}
        labels = {'miles': 'One-way miles (without odometer readings)'}

    def __init__(self, *args, branch, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.branch = branch
        self.fields['customer'].queryset = Customer.objects.filter(branch=branch)
        self.fields['property'].queryset = Property.objects.filter(customer__branch=branch)
        self.fields['work_entry'].queryset = WorkEntry.objects.filter(property__customer__branch=branch)
        for name in ['miles', 'odometer_start', 'odometer_finish']:
            self.fields[name].widget.attrs.update(inputmode='decimal', min='0', step='0.01')
        self.fields['miles'].help_text = 'Odometer distance overrides this field. Return doubles manual one-way miles only.'


class DailyMileageForm(forms.ModelForm):
    class Meta:
        model = MileageJourney
        fields = ['journey_date', 'odometer_start', 'odometer_finish', 'stops', 'purpose', 'private_miles', 'route_description']
        widgets = {
            'journey_date': DateInput(),
            'stops': forms.CheckboxSelectMultiple(),
        }
        labels = {
            'journey_date': 'Date', 'odometer_start': 'Start odometer',
            'odometer_finish': 'End odometer', 'stops': 'Properties visited (optional)',
            'private_miles': 'Private miles', 'route_description': 'Other stops / route (optional)',
        }
        help_texts = {
            'odometer_finish': 'Leave blank in the morning. Finish this same record at the end of the day.',
            'route_description': 'If you do not select properties, describe the business route here before approval.',
            'private_miles': 'Usually zero. Exclude any private driving or ordinary commuting included in the readings.',
        }

    def __init__(self, *args, branch='garden', **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.branch = branch
        self.instance.is_daily = True
        self.instance.start = 'Start of working day'
        self.instance.destination = 'Daily business round'
        self.instance.return_journey = False
        self.fields['odometer_start'].required = True
        self.fields['private_miles'].required = False
        if not self.instance.pk:
            self.initial['purpose'] = 'Garden & property maintenance' if branch == 'garden' else 'Rainwater harvesting site visits'
        self.fields['stops'].queryset = Property.objects.filter(customer__branch=branch).select_related('customer')
        self.fields['stops'].label_from_instance = lambda stop: f'{stop.customer.display_name} — {stop}'
        for name in ['odometer_start', 'odometer_finish', 'private_miles']:
            self.fields[name].widget.attrs.update(inputmode='decimal', min='0', step='0.01')

    def clean_private_miles(self):
        from decimal import Decimal
        return self.cleaned_data.get('private_miles') or Decimal('0')

    def clean(self):
        cleaned = super().clean()
        day = cleaned.get('journey_date')
        if day and MileageJourney.objects.filter(ledger_id=self.instance.ledger_id, journey_date=day).exclude(status='void').exclude(pk=self.instance.pk).exists():
            self.add_error('journey_date', 'Mileage already exists for this date. Finish or edit the existing record instead.')
        if cleaned.get('odometer_finish') is not None and not cleaned.get('stops') and not cleaned.get('route_description'):
            self.add_error('route_description', 'Select properties visited or enter a short business route.')
        return cleaned
