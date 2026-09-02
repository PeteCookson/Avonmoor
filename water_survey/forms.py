from decimal import Decimal

from django import forms

from .models import RoofSection, Survey, SystemAssessment
from .services.geometry import calculate_geojson_area_m2
from .services.rainfall import MONTHS


class SurveyForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.monthly_rainfall_mm:
            self.fields.pop('annual_rainfall_mm', None)

    class Meta:
        model = Survey
        fields = [
            'property_name',
            'address_line_1',
            'town',
            'postcode',
            'annual_rainfall_mm',
            'notes',
        ]
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }
        labels = {
            'annual_rainfall_mm': 'Manual annual rainfall fallback (mm)',
        }


class SurveyUpdateForm(SurveyForm):
    class Meta(SurveyForm.Meta):
        fields = [
            'property_name',
            'address_line_1',
            'town',
            'postcode',
            'annual_rainfall_mm',
            'status',
            'notes',
        ]


class RoofSectionForm(forms.ModelForm):
    map_latitude = forms.DecimalField(
        required=False,
        min_value=-90,
        max_value=90,
        decimal_places=6,
        widget=forms.HiddenInput(),
    )
    map_longitude = forms.DecimalField(
        required=False,
        min_value=-180,
        max_value=180,
        decimal_places=6,
        widget=forms.HiddenInput(),
    )

    class Meta:
        model = RoofSection
        fields = [
            'name',
            'downpipe_label',
            'roof_material',
            'area_m2',
            'runoff_coefficient',
            'system_efficiency',
            'polygon',
            'map_latitude',
            'map_longitude',
        ]
        widgets = {
            'polygon': forms.HiddenInput(),
            'area_m2': forms.NumberInput(
                attrs={'inputmode': 'decimal', 'step': '0.01', 'min': '0.01'}
            ),
        }
        labels = {
            'area_m2': 'Plan area (m²)',
            'runoff_coefficient': 'Runoff coefficient',
            'system_efficiency': 'System efficiency',
        }

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


class SystemAssessmentForm(forms.ModelForm):
    intended_uses = forms.MultipleChoiceField(
        choices=SystemAssessment.INTENDED_USE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        label='What will the rainwater supply?',
    )
    site_constraints = forms.MultipleChoiceField(
        choices=SystemAssessment.SITE_CONSTRAINT_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Known site constraints',
    )

    class Meta:
        model = SystemAssessment
        fields = [
            'intended_uses',
            'demand_basis',
            'occupants',
            'tank_location',
            'system_type',
            'access_rating',
            'site_constraints',
            'overflow_destination',
            'power_available',
            'maximum_storage_litres',
            'proposed_storage_litres',
            'route_notes',
            'assessment_notes',
        ]
        widgets = {
            'route_notes': forms.Textarea(attrs={'rows': 3}),
            'assessment_notes': forms.Textarea(attrs={'rows': 4}),
            'occupants': forms.NumberInput(
                attrs={'min': '1', 'inputmode': 'numeric'}
            ),
            'maximum_storage_litres': forms.NumberInput(
                attrs={'min': '1', 'step': '1', 'inputmode': 'numeric'}
            ),
            'proposed_storage_litres': forms.NumberInput(
                attrs={'min': '1', 'step': '1', 'inputmode': 'numeric'}
            ),
        }
        labels = {
            'demand_basis': 'Demand evidence',
            'occupants': 'Household occupants (if relevant)',
            'tank_location': 'Likely tank location',
            'system_type': 'Likely system type',
            'access_rating': 'Installation access',
            'overflow_destination': 'Likely overflow destination',
            'power_available': 'Electrical supply',
            'maximum_storage_litres': 'Maximum practical storage (litres)',
            'proposed_storage_litres': 'Storage capacity to model (litres)',
            'route_notes': 'Gutters, downpipes, pipe routes and overflow notes',
            'assessment_notes': 'Demand assumptions and assessment notes',
        }
        help_texts = {
            'maximum_storage_litres': (
                'Leave blank until space, access and installation limits are known.'
            ),
            'proposed_storage_litres': (
                'Optional. Leave blank to model the preliminary 18-day capacity.'
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        monthly_values = (
            self.instance.normalised_monthly_demand
            if self.instance and self.instance.pk
            else {}
        )
        for key, label in MONTHS:
            self.fields[f'{key}_demand_litres'] = forms.DecimalField(
                min_value=0,
                max_digits=12,
                decimal_places=2,
                initial=monthly_values.get(key, 0),
                label=f'{label} demand (litres)',
                widget=forms.NumberInput(
                    attrs={
                        'min': '0',
                        'step': '1',
                        'inputmode': 'decimal',
                    }
                ),
            )

        month_fields = [f'{key}_demand_litres' for key, _ in MONTHS]
        self.order_fields([
            'intended_uses',
            'demand_basis',
            'occupants',
            *month_fields,
            'tank_location',
            'system_type',
            'access_rating',
            'site_constraints',
            'overflow_destination',
            'power_available',
            'maximum_storage_litres',
            'proposed_storage_litres',
            'route_notes',
            'assessment_notes',
        ])

    def clean(self):
        cleaned_data = super().clean()
        monthly = {}
        for key, _ in MONTHS:
            value = cleaned_data.get(f'{key}_demand_litres')
            if value is not None:
                monthly[key] = str(value)

        if len(monthly) == len(MONTHS) and not any(
            value > 0 for value in map(Decimal, monthly.values())
        ):
            self.add_error(
                'jan_demand_litres',
                'Enter expected demand in at least one month.',
            )

        cleaned_data['monthly_demand_litres'] = monthly
        self.instance.monthly_demand_litres = monthly
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.monthly_demand_litres = self.cleaned_data[
            'monthly_demand_litres'
        ]
        if commit:
            instance.save()
        return instance
