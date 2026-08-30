from django import forms

from .models import RoofSection, Survey
from .services.geometry import calculate_geojson_area_m2


class SurveyForm(forms.ModelForm):
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
