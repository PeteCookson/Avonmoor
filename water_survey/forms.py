from django import forms

from .models import RoofSection, Survey


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
            'annual_rainfall_mm': 'Annual rainfall (mm)',
        }


class RoofSectionForm(forms.ModelForm):
    class Meta:
        model = RoofSection
        fields = [
            'name',
            'downpipe_label',
            'roof_material',
            'area_m2',
            'runoff_coefficient',
            'system_efficiency',
        ]
        labels = {
            'area_m2': 'Plan area (m²)',
            'runoff_coefficient': 'Runoff coefficient',
            'system_efficiency': 'System efficiency',
        }
