import uuid
from decimal import Decimal
from functools import cached_property

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from .services.calculations import (
    calculate_preliminary_storage_litres,
    calculate_yield_litres,
    normalise_monthly_demand,
    simulate_storage_balance,
)
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
        help_text='GeoJSON roof outline captured by the map tool.',
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


class SystemAssessment(models.Model):
    class DemandBasis(models.TextChoices):
        CUSTOMER = 'customer', 'Customer estimate'
        FIXTURE = 'fixture', 'Fixture and usage estimate'
        METERED = 'metered', 'Measured or metered use'
        OTHER = 'other', 'Other evidence'

    class TankLocation(models.TextChoices):
        UNASSESSED = 'unassessed', 'Not assessed'
        ABOVE_GROUND = 'above_ground', 'Above ground'
        BELOW_GROUND = 'below_ground', 'Below ground'
        INTERNAL = 'internal', 'Inside an outbuilding'
        MIXED = 'mixed', 'Combined storage locations'

    class SystemType(models.TextChoices):
        UNASSESSED = 'unassessed', 'Not assessed'
        GRAVITY = 'gravity', 'Gravity-fed above-ground system'
        ABOVE_GROUND_PUMPED = 'above_pumped', 'Pumped above-ground system'
        BELOW_GROUND_PUMPED = 'below_pumped', 'Pumped below-ground system'
        HEADER_TANK = 'header_tank', 'Pumped system with header tank'
        BESPOKE = 'bespoke', 'Bespoke or commercial system'

    class AccessRating(models.TextChoices):
        UNASSESSED = 'unassessed', 'Not assessed'
        GOOD = 'good', 'Good plant and delivery access'
        RESTRICTED = 'restricted', 'Restricted access'
        HAND_DIG = 'hand_dig', 'Hand excavation likely'
        SPECIALIST = 'specialist', 'Specialist lifting or excavation required'

    class OverflowDestination(models.TextChoices):
        UNASSESSED = 'unassessed', 'Not assessed'
        SOAKAWAY = 'soakaway', 'Soakaway or infiltration area'
        SURFACE_WATER = 'surface_water', 'Surface-water drainage'
        WATERCOURSE = 'watercourse', 'Watercourse or pond'
        GARDEN = 'garden', 'Controlled discharge to garden'
        OTHER = 'other', 'Other or requires investigation'

    class PowerAvailability(models.TextChoices):
        UNKNOWN = 'unknown', 'Not assessed'
        YES = 'yes', 'Suitable supply available'
        NO = 'no', 'No suitable supply available'

    INTENDED_USE_CHOICES = (
        ('garden', 'Garden watering'),
        ('vehicles', 'Vehicle washing'),
        ('toilets', 'Toilet flushing'),
        ('laundry', 'Washing machine'),
        ('livestock', 'Livestock watering'),
        ('commercial', 'Commercial or operational use'),
        ('other', 'Other non-potable use'),
    )
    SITE_CONSTRAINT_CHOICES = (
        ('narrow_access', 'Narrow access'),
        ('limited_excavator', 'Limited excavator access'),
        ('slope', 'Sloping ground'),
        ('clay', 'Clay ground'),
        ('rock', 'Rock or difficult excavation'),
        ('high_water_table', 'High water table or flood risk'),
        ('services', 'Buried services'),
        ('tree_roots', 'Trees or protected root zones'),
        ('listed_property', 'Listed building or planning sensitivity'),
    )

    survey = models.OneToOneField(
        Survey,
        on_delete=models.CASCADE,
        related_name='system_assessment',
    )
    intended_uses = models.JSONField(default=list)
    demand_basis = models.CharField(
        max_length=20,
        choices=DemandBasis.choices,
        default=DemandBasis.CUSTOMER,
    )
    occupants = models.PositiveSmallIntegerField(null=True, blank=True)
    monthly_demand_litres = models.JSONField(default=dict)
    tank_location = models.CharField(
        max_length=20,
        choices=TankLocation.choices,
        default=TankLocation.UNASSESSED,
    )
    system_type = models.CharField(
        max_length=20,
        choices=SystemType.choices,
        default=SystemType.UNASSESSED,
    )
    access_rating = models.CharField(
        max_length=20,
        choices=AccessRating.choices,
        default=AccessRating.UNASSESSED,
    )
    site_constraints = models.JSONField(default=list, blank=True)
    overflow_destination = models.CharField(
        max_length=20,
        choices=OverflowDestination.choices,
        default=OverflowDestination.UNASSESSED,
    )
    power_available = models.CharField(
        max_length=10,
        choices=PowerAvailability.choices,
        default=PowerAvailability.UNKNOWN,
    )
    maximum_storage_litres = models.PositiveIntegerField(null=True, blank=True)
    proposed_storage_litres = models.PositiveIntegerField(null=True, blank=True)
    route_notes = models.TextField(blank=True)
    assessment_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f'System assessment for {self.survey}'

    def clean(self):
        errors = {}
        valid_uses = {value for value, _ in self.INTENDED_USE_CHOICES}
        if not isinstance(self.intended_uses, list):
            errors['intended_uses'] = 'Select one or more intended uses.'
        elif not self.intended_uses:
            errors['intended_uses'] = 'Select at least one intended use.'
        elif set(self.intended_uses) - valid_uses:
            errors['intended_uses'] = 'One or more intended uses are invalid.'

        valid_constraints = {value for value, _ in self.SITE_CONSTRAINT_CHOICES}
        if not isinstance(self.site_constraints, list):
            errors['site_constraints'] = 'Site constraints must be a list.'
        elif set(self.site_constraints) - valid_constraints:
            errors['site_constraints'] = (
                'One or more site constraints are invalid.'
            )

        try:
            normalise_monthly_demand(self.monthly_demand_litres)
        except ValueError as error:
            errors['monthly_demand_litres'] = str(error)

        if (
            self.maximum_storage_litres
            and self.proposed_storage_litres
            and self.proposed_storage_litres > self.maximum_storage_litres
        ):
            errors['proposed_storage_litres'] = (
                'The proposed storage exceeds the recorded site maximum.'
            )

        if errors:
            raise ValidationError(errors)

    @property
    def normalised_monthly_demand(self):
        try:
            return normalise_monthly_demand(self.monthly_demand_litres)
        except ValueError:
            return {}

    @property
    def annual_demand_litres(self):
        return sum(self.normalised_monthly_demand.values(), Decimal('0'))

    @property
    def intended_use_labels(self):
        labels = dict(self.INTENDED_USE_CHOICES)
        return [labels[value] for value in self.intended_uses if value in labels]

    @property
    def site_constraint_labels(self):
        labels = dict(self.SITE_CONSTRAINT_CHOICES)
        return [
            labels[value] for value in self.site_constraints if value in labels
        ]

    @property
    def preliminary_storage_litres(self):
        annual_yield = self.survey.estimated_annual_yield_litres
        if annual_yield is None:
            return None
        return calculate_preliminary_storage_litres(
            annual_yield=annual_yield,
            annual_demand=self.annual_demand_litres,
        )

    @property
    def analysis_capacity_litres(self):
        return self.proposed_storage_litres or self.preliminary_storage_litres

    @property
    def storage_exceeds_site_maximum(self):
        return bool(
            self.maximum_storage_litres
            and self.preliminary_storage_litres
            and self.preliminary_storage_litres > self.maximum_storage_litres
        )

    @cached_property
    def water_balance(self):
        capacity = self.analysis_capacity_litres
        monthly_yields = {
            row['key']: row['yield_litres']
            for row in self.survey.monthly_yield_rows
        }
        if not capacity or not monthly_yields or not self.normalised_monthly_demand:
            return None

        balance = simulate_storage_balance(
            monthly_yield_litres=monthly_yields,
            monthly_demand_litres=self.normalised_monthly_demand,
            capacity_litres=capacity,
        )
        month_labels = dict(MONTHS)
        for row in balance['rows']:
            row['month'] = month_labels[row['key']]
        return balance
