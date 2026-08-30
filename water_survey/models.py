import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from .services.calculations import calculate_yield_litres
from .services.rainfall import MONTHS, normalise_monthly_rainfall


class RainfallGridPoint(models.Model):
    """A locally cached long-term rainfall climatology grid point."""

    grid_reference = models.CharField(max_length=80, unique=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, db_index=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, db_index=True)
    monthly_rainfall_mm = models.JSONField()
    annual_rainfall_mm = models.DecimalField(max_digits=7, decimal_places=2)
    source_name = models.CharField(max_length=120, default='Met Office HadUK-Grid')
    source_version = models.CharField(max_length=40, blank=True)
    reference_period = models.CharField(max_length=20, default='1991-2020')
    resolution_km = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['grid_reference']
        indexes = [
            models.Index(
                fields=['latitude', 'longitude'],
                name='rain_grid_lat_lon_idx',
            )
        ]

    def __str__(self):
        return f'{self.grid_reference} ({self.reference_period})'

    def clean(self):
        errors = {}
        try:
            monthly = normalise_monthly_rainfall(self.monthly_rainfall_mm)
        except ValueError as error:
            errors['monthly_rainfall_mm'] = str(error)
        else:
            expected_annual = sum(monthly.values(), Decimal('0'))
            if (
                self.annual_rainfall_mm is not None
                and abs(expected_annual - self.annual_rainfall_mm)
                > Decimal('0.12')
            ):
                errors['annual_rainfall_mm'] = (
                    'Annual rainfall must equal the sum of the 12 monthly values.'
                )

        if errors:
            raise ValidationError(errors)


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
        help_text='Optional manual fallback when local climate data is unavailable.',
    )
    monthly_rainfall_mm = models.JSONField(default=dict, blank=True)
    rainfall_grid_point = models.ForeignKey(
        RainfallGridPoint,
        on_delete=models.SET_NULL,
        related_name='surveys',
        null=True,
        blank=True,
    )
    rainfall_source = models.CharField(max_length=180, blank=True)
    rainfall_reference_period = models.CharField(max_length=20, blank=True)
    rainfall_distance_km = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    rainfall_updated_at = models.DateTimeField(null=True, blank=True)
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

    @property
    def monthly_yield_rows(self):
        if not self.monthly_rainfall_mm:
            return []

        try:
            rainfall = normalise_monthly_rainfall(self.monthly_rainfall_mm)
        except ValueError:
            return []

        roofs = list(self.roof_sections.all())
        return [
            {
                'key': key,
                'month': label,
                'rainfall_mm': rainfall[key],
                'yield_litres': sum(
                    (roof.calculate_yield(rainfall[key]) for roof in roofs),
                    Decimal('0'),
                ),
            }
            for key, label in MONTHS
        ]


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
