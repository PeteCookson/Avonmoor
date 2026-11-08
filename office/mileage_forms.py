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
