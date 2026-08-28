from django.contrib import admin

from .models import RoofSection, Survey


class RoofSectionInline(admin.TabularInline):
    model = RoofSection
    extra = 0


@admin.register(Survey)
class SurveyAdmin(admin.ModelAdmin):
    list_display = (
        'address_line_1',
        'postcode',
        'status',
        'created_by',
        'updated_at',
    )
    list_filter = ('status', 'updated_at')
    search_fields = ('property_name', 'address_line_1', 'postcode')
    readonly_fields = ('reference', 'created_at', 'updated_at')
    inlines = (RoofSectionInline,)
