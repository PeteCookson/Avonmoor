import uuid

from django.db import models

from water_survey.models import RoofSection

from .constants import INTENDED_USE_CHOICES


class CustomerSurveyLead(models.Model):
    class Status(models.TextChoices):
        NEW = 'new', 'New'
        SURVEY_REQUESTED = 'survey_requested', 'Survey Requested'
        CONTACTED = 'contacted', 'Contacted'
        SURVEY_BOOKED = 'survey_booked', 'Survey Booked'
        SURVEYED = 'surveyed', 'Surveyed'
        QUOTED = 'quoted', 'Quoted'
        WON = 'won', 'Won'
        LOST = 'lost', 'Lost'

    class PreferredContact(models.TextChoices):
        EMAIL = 'email', 'Email'
        PHONE = 'phone', 'Phone'

    class LocationMethod(models.TextChoices):
        MAP = 'map', 'Mapped roof location'
        POSTCODE = 'postcode', 'Approximate postcode centre'

    reference = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.NEW
    )
    survey = models.OneToOneField(
        'water_survey.Survey',
        on_delete=models.SET_NULL,
        related_name='calculator_lead',
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    preferred_contact = models.CharField(
        max_length=10,
        choices=PreferredContact.choices,
        default=PreferredContact.EMAIL,
    )
    address_line_1 = models.CharField(max_length=160)
    town = models.CharField(max_length=100, blank=True)
    postcode = models.CharField(max_length=12)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    roof_area_m2 = models.DecimalField(max_digits=8, decimal_places=2)
    roof_polygon = models.JSONField(default=dict, blank=True)
    roof_material = models.CharField(
        max_length=20, choices=RoofSection.RoofMaterial.choices
    )
    runoff_coefficient = models.DecimalField(
        max_digits=4, decimal_places=3, null=True, blank=True
    )
    system_efficiency = models.DecimalField(
        max_digits=4, decimal_places=3, null=True, blank=True
    )
    intended_use = models.CharField(max_length=30, choices=INTENDED_USE_CHOICES)
    has_existing_collection = models.BooleanField(default=False)
    location_method = models.CharField(
        max_length=12,
        choices=LocationMethod.choices,
        default=LocationMethod.MAP,
    )
    annual_rainfall_mm = models.DecimalField(max_digits=7, decimal_places=2)
    gross_rainfall_litres = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    estimated_annual_harvest_litres = models.DecimalField(
        max_digits=12, decimal_places=2
    )
    uncaptured_litres = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    indicative_storage_low_litres = models.PositiveIntegerField()
    indicative_storage_high_litres = models.PositiveIntegerField(null=True)
    rainfall_source = models.CharField(max_length=180)
    rainfall_reference_period = models.CharField(max_length=20)
    rainfall_distance_km = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    monthly_estimate = models.JSONField(default=list, blank=True)
    customer_message = models.TextField(blank=True)
    internal_notes = models.TextField(blank=True)
    consented_at = models.DateTimeField()
    survey_requested_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} - {self.postcode}'
