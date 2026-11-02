from django.contrib import admin

from .models import Customer, Invoice, InvoiceLine, InvoiceSequence, Property, WorkEntry


class PropertyInline(admin.TabularInline):
    model = Property
    extra = 0


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'contact_name', 'postcode', 'email', 'active')
    list_filter = ('active',)
    search_fields = ('display_name', 'contact_name', 'email', 'postcode')
    inlines = (PropertyInline,)


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'customer', 'town', 'postcode', 'active')
    list_filter = ('active',)
    search_fields = ('name', 'address_line_1', 'postcode', 'customer__display_name')


@admin.register(WorkEntry)
class WorkEntryAdmin(admin.ModelAdmin):
    list_display = (
        'service_date',
        'property',
        'category',
        'description',
        'quantity',
        'unit_price',
    )
    list_filter = ('category', 'service_date')
    search_fields = ('description', 'property__customer__display_name')


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 0
    readonly_fields = ()

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.status != Invoice.Status.DRAFT:
            return (
                'work_entry',
                'service_date',
                'category',
                'description',
                'quantity',
                'unit',
                'unit_price',
                'sort_order',
            )
        return ()

    def has_delete_permission(self, request, obj=None):
        return not obj or obj.status == Invoice.Status.DRAFT


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('display_number', 'customer', 'issue_date', 'status', 'total')
    list_filter = ('status', 'issue_date')
    search_fields = ('number', 'customer__display_name')
    readonly_fields = (
        'number',
        'customer_snapshot',
        'property_snapshot',
        'issued_at',
        'paid_at',
        'cancelled_at',
        'created_at',
        'updated_at',
    )
    inlines = (InvoiceLineInline,)


@admin.register(InvoiceSequence)
class InvoiceSequenceAdmin(admin.ModelAdmin):
    list_display = ('year', 'last_number')
    ordering = ('-year',)
