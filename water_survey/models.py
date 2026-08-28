import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from .services.calculations import calculate_yield_litres


class Survey(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        SURVEYED = 'surveyed', 'Surveyed'
        QUOTED = 'quoted', 'Quoted'

    reference = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='water_surveys',
    )
    property_name = models.CharField(max_length=120, blank=True)
    address_line_1 = models.CharField(max_length=160)
    town = models.CharField(max_length=100, blank=True)
    postcode = models.CharField(max_length=12)
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    annual_rainfall_mm = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Temporary manual value until the rainfall data import is connected.',
    )
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.DRAFT
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return self.property_name or f'{self.address_line_1}, {self.postcode}'

    @property
    def total_roof_area_m2(self):
        return sum(
            (section.area_m2 for section in self.roof_sections.all()),
            Decimal('0'),
        )

    @property
    def estimated_annual_yield_litres(self):
        if self.annual_rainfall_mm is None:
            return None

        return sum(
            (
                section.calculate_yield(self.annual_rainfall_mm)
                for section in self.roof_sections.all()
            ),
            Decimal('0'),
        )


class RoofSection(models.Model):
    class RoofMaterial(models.TextChoices):
        METAL = 'metal', 'Metal or smooth sheet'
        SLATE_TILE = 'slate_tile', 'Slate or tile'
        ROUGH_TILE = 'rough_tile', 'Rough concrete tile'
        GREEN = 'green', 'Green roof'
        OTHER = 'other', 'Other'

    survey = models.ForeignKey(
        Survey, on_delete=models.CASCADE, related_name='roof_sections'
    )
    name = models.CharField(max_length=80, default='Main roof')
    downpipe_label = models.CharField(max_length=80, blank=True)
    roof_material = models.CharField(
        max_length=20,
        choices=RoofMaterial.choices,
        default=RoofMaterial.SLATE_TILE,
    )
    area_m2 = models.DecimalField(max_digits=8, decimal_places=2)
    runoff_coefficient = models.DecimalField(
        max_digits=4,
        decimal_places=3,
        default=Decimal('0.850'),
        help_text='Fraction of rainfall expected to run off the roof.',
    )
    system_efficiency = models.DecimalField(
        max_digits=4,
        decimal_places=3,
        default=Decimal('0.950'),
        help_text='Allowance for filters, first flush and other losses.',
    )
    polygon = models.JSONField(
        default=dict,
        blank=True,
        help_text='GeoJSON roof outline. Populated by the map tool in the next stage.',
    )
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'id']

    def __str__(self):
        return f'{self.survey}: {self.name}'

    def clean(self):
        errors = {}
        if self.area_m2 is not None and self.area_m2 <= 0:
            errors['area_m2'] = 'Roof area must be greater than zero.'

        for field_name in ('runoff_coefficient', 'system_efficiency'):
            value = getattr(self, field_name)
            if value is not None and not Decimal('0') <= value <= Decimal('1'):
                errors[field_name] = 'Enter a value between 0 and 1.'

        if self.polygon and not isinstance(self.polygon, dict):
            errors['polygon'] = 'Roof polygon must be a GeoJSON object.'

        if errors:
            raise ValidationError(errors)

    def calculate_yield(self, rainfall_mm):
        return calculate_yield_litres(
            area_m2=self.area_m2,
            rainfall_mm=rainfall_mm,
            runoff_coefficient=self.runoff_coefficient,
            system_efficiency=self.system_efficiency,
        )

    @property
    def estimated_annual_yield_litres(self):
        if self.survey.annual_rainfall_mm is None:
            return None
        return self.calculate_yield(self.survey.annual_rainfall_mm)
