from django.contrib import admin

from .models import RainfallGridPoint, RoofSection, Survey, SystemAssessment


@admin.register(RainfallGridPoint)
class RainfallGridPointAdmin(admin.ModelAdmin):
    list_display = (
        'grid_reference',
        'reference_period',
        'annual_rainfall_mm',
        'resolution_km',
    )
    list_filter = ('reference_period', 'source_version', 'resolution_km')
    search_fields = ('grid_reference',)
    readonly_fields = ('imported_at',)


class RoofSectionInline(admin.TabularInline):
    model = RoofSection
    extra = 0


class SystemAssessmentInline(admin.StackedInline):
    model = SystemAssessment
    extra = 0
    max_num = 1


@admin.register(Survey)
class SurveyAdmin(admin.ModelAdmin):
    list_display = (
        'address_line_1',
        'postcode',
        'status',
        'annual_rainfall_mm',
        'created_by',
        'updated_at',
    )
    list_filter = ('status', 'updated_at')
    search_fields = ('property_name', 'address_line_1', 'postcode')
    readonly_fields = (
        'reference',
        'rainfall_updated_at',
        'created_at',
        'updated_at',
    )
    inlines = (RoofSectionInline, SystemAssessmentInline)
