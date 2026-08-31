from django.contrib import admin

from .models import CustomerSurveyLead


@admin.register(CustomerSurveyLead)
class CustomerSurveyLeadAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'postcode',
        'estimated_annual_harvest_litres',
        'status',
        'created_at',
    )
    list_filter = ('status', 'intended_use', 'created_at')
    search_fields = ('name', 'email', 'phone', 'postcode', 'address_line_1')
    readonly_fields = ('reference', 'consented_at', 'created_at', 'updated_at')
