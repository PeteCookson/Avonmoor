import uuid

from django.db import models

from water_survey.models import RoofSection

from .constants import INTENDED_USE_CHOICES


class CustomerSurveyLead(models.Model):
    class Status(models.TextChoices):
        NEW = 'new', 'New'
        CONTACTED = 'contacted', 'Contacted'
        QUALIFIED = 'qualified', 'Qualified'
        CLOSED = 'closed', 'Closed'

    class PreferredContact(models.TextChoices):
        EMAIL = 'email', 'Email'
        PHONE = 'phone', 'Phone'

    reference = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.NEW
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
    intended_use = models.CharField(max_length=30, choices=INTENDED_USE_CHOICES)
    has_existing_collection = models.BooleanField(default=False)
    annual_rainfall_mm = models.DecimalField(max_digits=7, decimal_places=2)
    estimated_annual_harvest_litres = models.DecimalField(
        max_digits=12, decimal_places=2
    )
    indicative_storage_low_litres = models.PositiveIntegerField()
    indicative_storage_high_litres = models.PositiveIntegerField(null=True)
    rainfall_source = models.CharField(max_length=180)
    rainfall_reference_period = models.CharField(max_length=20)
    customer_message = models.TextField(blank=True)
    consented_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} - {self.postcode}'
