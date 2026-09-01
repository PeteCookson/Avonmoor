from django.contrib import admin, messages
from django.db import transaction
from django.urls import reverse
from django.utils.html import format_html

from water_survey.models import RoofSection, Survey

from .models import CustomerSurveyLead
from .services import RUNOFF_COEFFICIENTS, SYSTEM_EFFICIENCY


@admin.register(CustomerSurveyLead)
class CustomerSurveyLeadAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'postcode',
        'status',
        'survey_requested_at',
        'estimated_annual_harvest_litres',
        'survey_link',
        'created_at',
    )
    list_editable = ('status',)
    list_filter = (
        'status',
        'intended_use',
        'roof_material',
        'has_existing_collection',
        'created_at',
    )
    search_fields = ('name', 'email', 'phone', 'postcode', 'address_line_1')
    readonly_fields = (
        'reference',
        'survey_link',
        'consented_at',
        'survey_requested_at',
        'created_at',
        'updated_at',
    )
    actions = ('create_survey_records',)
    date_hierarchy = 'created_at'
    fieldsets = (
        ('Lead', {
            'fields': (
                'reference', 'status', 'name', 'email', 'phone',
                'preferred_contact', 'customer_message', 'internal_notes',
                'consented_at', 'survey_requested_at',
            ),
        }),
        ('Property', {
            'fields': (
                'address_line_1', 'town', 'postcode', 'latitude', 'longitude',
                'location_method',
            ),
        }),
        ('Calculator Snapshot', {
            'fields': (
                'roof_area_m2', 'roof_polygon', 'roof_material',
                'runoff_coefficient', 'system_efficiency', 'intended_use',
                'has_existing_collection', 'annual_rainfall_mm',
                'gross_rainfall_litres', 'estimated_annual_harvest_litres',
                'uncaptured_litres', 'indicative_storage_low_litres',
                'indicative_storage_high_litres', 'rainfall_source',
                'rainfall_reference_period', 'rainfall_distance_km',
                'monthly_estimate',
            ),
        }),
        ('Survey Workflow', {
            'fields': ('survey', 'survey_link', 'created_at', 'updated_at'),
        }),
    )

    @admin.display(description='Survey')
    def survey_link(self, lead):
        if not lead.survey_id:
            return 'Not created'
        url = reverse('water_survey:survey-detail', args=[lead.survey_id])
        return format_html('<a href="{}">Open survey</a>', url)

    @admin.action(description='Create survey records from selected leads')
    def create_survey_records(self, request, queryset):
        created_count = 0
        skipped_count = 0
        for lead in queryset.select_related('survey'):
            if lead.survey_id:
                skipped_count += 1
                continue

            monthly_rainfall = {
                row['key']: row['rainfall_mm']
                for row in lead.monthly_estimate
                if isinstance(row, dict)
                and row.get('key')
                and row.get('rainfall_mm') is not None
            }
            with transaction.atomic():
                survey = Survey.objects.create(
                    created_by=request.user,
                    address_line_1=lead.address_line_1,
                    town=lead.town,
                    postcode=lead.postcode,
                    latitude=lead.latitude,
                    longitude=lead.longitude,
                    annual_rainfall_mm=lead.annual_rainfall_mm,
                    monthly_rainfall_mm=monthly_rainfall,
                    rainfall_source=lead.rainfall_source,
                    rainfall_reference_period=lead.rainfall_reference_period,
                    rainfall_distance_km=lead.rainfall_distance_km,
                )
                RoofSection.objects.create(
                    survey=survey,
                    name='Calculator roof',
                    roof_material=lead.roof_material,
                    area_m2=lead.roof_area_m2,
                    runoff_coefficient=(
                        lead.runoff_coefficient
                        or RUNOFF_COEFFICIENTS[lead.roof_material]
                    ),
                    system_efficiency=(
                        lead.system_efficiency or SYSTEM_EFFICIENCY
                    ),
                    polygon=lead.roof_polygon,
                )
                lead.survey = survey
                lead.save(update_fields=['survey', 'updated_at'])
            created_count += 1

        if created_count:
            self.message_user(
                request,
                f'{created_count} survey record(s) created with calculator '
                'measurements and rainfall data.',
                level=messages.SUCCESS,
            )
        if skipped_count:
            self.message_user(
                request,
                f'{skipped_count} lead(s) already had a survey and were skipped.',
                level=messages.WARNING,
            )
