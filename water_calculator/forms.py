from django import forms

from water_survey.models import RoofSection
from water_survey.services.geometry import calculate_geojson_area_m2

from .constants import INTENDED_USE_CHOICES
from .models import CustomerSurveyLead


class PropertyForm(forms.Form):
    address_line_1 = forms.CharField(
        max_length=160,
        label='Property address',
        widget=forms.TextInput(attrs={'autocomplete': 'address-line1'}),
    )
    town = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'autocomplete': 'address-level2'}),
    )
    postcode = forms.CharField(
        max_length=12,
        widget=forms.TextInput(
            attrs={'autocomplete': 'postal-code', 'autocapitalize': 'characters'}
        ),
    )

    def clean_postcode(self):
        return ' '.join(self.cleaned_data['postcode'].upper().split())


class RoofEstimateForm(forms.Form):
    polygon = forms.JSONField(required=False, widget=forms.HiddenInput())
    map_latitude = forms.DecimalField(
        min_value=-90,
        max_value=90,
        decimal_places=6,
        widget=forms.HiddenInput(),
    )
    map_longitude = forms.DecimalField(
        min_value=-180,
        max_value=180,
        decimal_places=6,
        widget=forms.HiddenInput(),
    )
    area_m2 = forms.DecimalField(
        min_value=0.01,
        max_digits=8,
        decimal_places=2,
        label='Selected roof area (m²)',
        widget=forms.NumberInput(
            attrs={'inputmode': 'decimal', 'step': '0.01', 'min': '0.01'}
        ),
    )
    roof_material = forms.ChoiceField(
        choices=RoofSection.RoofMaterial.choices,
        initial=RoofSection.RoofMaterial.SLATE_TILE,
    )
    intended_use = forms.ChoiceField(
        choices=INTENDED_USE_CHOICES,
        widget=forms.RadioSelect(),
        label='What would you use the stored rainwater for?',
    )
    has_existing_collection = forms.TypedChoiceField(
        choices=((False, 'No'), (True, 'Yes')),
        coerce=lambda value: value == 'True',
        widget=forms.RadioSelect(),
        label='Do you already collect rainwater from this roof?',
    )

    def clean(self):
        cleaned_data = super().clean()
        polygon = cleaned_data.get('polygon')
        if not polygon:
            return cleaned_data
        try:
            cleaned_data['area_m2'] = calculate_geojson_area_m2(polygon)
        except ValueError as error:
            self.add_error('polygon', str(error))
        return cleaned_data


class SurveyRequestForm(forms.ModelForm):
    website = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={'tabindex': '-1', 'autocomplete': 'off', 'aria-hidden': 'true'}
        ),
    )
    consent = forms.BooleanField(
        label=(
            'I agree that Avonmoor may use these details to respond to my '
            'survey request.'
        )
    )

    class Meta:
        model = CustomerSurveyLead
        fields = [
            'name',
            'email',
            'phone',
            'preferred_contact',
            'customer_message',
        ]
        widgets = {
            'email': forms.EmailInput(attrs={'autocomplete': 'email'}),
            'phone': forms.TextInput(attrs={'autocomplete': 'tel'}),
            'customer_message': forms.Textarea(attrs={'rows': 3}),
        }
        labels = {
            'customer_message': 'Anything we should know? (optional)',
        }

    def clean_website(self):
        value = self.cleaned_data.get('website', '')
        if value:
            raise forms.ValidationError('Unable to submit this request.')
        return value

    def clean(self):
        cleaned_data = super().clean()
        if (
            cleaned_data.get('preferred_contact')
            == CustomerSurveyLead.PreferredContact.PHONE
            and not cleaned_data.get('phone')
        ):
            self.add_error('phone', 'Enter a phone number for a phone response.')
        return cleaned_data
