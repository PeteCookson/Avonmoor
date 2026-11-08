from django.contrib import admin

from .models import (
    BankConnection,
    BankTransaction,
    Customer,
    Expense,
    ExpenseImportRule,
    Invoice,
    InvoiceEmail,
    InvoiceLine,
    InvoiceSequence,
    PaymentMatch,
    Property,
    WorkEntry,
)


class PropertyInline(admin.TabularInline):
    model = Property
    extra = 0


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'branch', 'contact_name', 'postcode', 'email', 'active')
    list_filter = ('branch', 'active')
    search_fields = ('display_name', 'contact_name', 'email', 'postcode')
    inlines = (PropertyInline,)


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'customer', 'town', 'postcode', 'active')
    list_filter = ('customer__branch', 'active')
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
    list_filter = ('property__customer__branch', 'category', 'service_date')
    search_fields = ('description', 'property__customer__display_name')


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    def has_delete_permission(self, request, obj=None):
        return False

    list_display = (
        'expense_date',
        'branch',
        'supplier',
        'category',
        'amount',
        'voided_at',
    )
    list_filter = ('branch', 'category', 'payment_method', 'voided_at')
    search_fields = (
        'supplier',
        'description',
        'reference',
        'property__customer__display_name',
    )
    readonly_fields = (
        'branch',
        'expense_date',
        'supplier',
        'category',
        'description',
        'property',
        'amount',
        'payment_method',
        'reference',
        'notes',
        'bank_transaction',
        'created_by',
        'updated_by',
        'voided_at',
        'voided_by',
        'created_at',
        'updated_at',
    )

    def has_add_permission(self, request):
        return False


@admin.register(ExpenseImportRule)
class ExpenseImportRuleAdmin(admin.ModelAdmin):
    list_display = ('match_text', 'supplier', 'branch', 'category', 'active')
    list_filter = ('branch', 'category', 'active')
    search_fields = ('match_text', 'supplier', 'description')


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
    list_display = ('display_number', 'branch', 'customer', 'issue_date', 'status', 'total')
    list_filter = ('branch', 'status', 'issue_date')
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
    list_display = ('branch', 'year', 'last_number')
    ordering = ('-year',)


@admin.register(InvoiceEmail)
class InvoiceEmailAdmin(admin.ModelAdmin):
    list_display = ('invoice', 'recipient', 'sent_at', 'sent_by')
    search_fields = ('invoice__number', 'recipient', 'subject')
    readonly_fields = ('invoice', 'recipient', 'subject', 'body', 'sent_by', 'sent_at')

    def has_add_permission(self, request):
        return False


@admin.register(BankConnection)
class BankConnectionAdmin(admin.ModelAdmin):
    list_display = ('provider', 'account_name', 'active', 'last_synced_at')
    readonly_fields = (
        'provider',
        'account_id',
        'account_name',
        'access_token_encrypted',
        'refresh_token_encrypted',
        'token_expires_at',
        'webhook_id',
        'active',
        'connected_by',
        'last_synced_at',
        'created_at',
        'updated_at',
    )

    def has_add_permission(self, request):
        return False


@admin.register(BankTransaction)
class BankTransactionAdmin(admin.ModelAdmin):
    list_display = (
        'transaction_at',
        'description',
        'amount',
        'source',
        'review_status',
    )
    list_filter = ('source', 'currency', 'ignored_at')
    search_fields = ('external_id', 'description', 'reference')
    readonly_fields = (
        'source',
        'external_id',
        'account_id',
        'amount_minor',
        'currency',
        'transaction_at',
        'settled_at',
        'description',
        'reference',
        'raw_data',
        'ignored_at',
        'ignored_by',
        'imported_at',
        'updated_at',
    )

    def has_add_permission(self, request):
        return False


@admin.register(PaymentMatch)
class PaymentMatchAdmin(admin.ModelAdmin):
    list_display = ('transaction', 'invoice', 'method', 'matched_at', 'matched_by')
    readonly_fields = (
        'transaction', 'invoice', 'method', 'matched_at', 'matched_by'
    )

    def has_add_permission(self, request):
        return False


from .models import MileageLedger, MileageJourney, MileageClaim, MileageClaimLine


class MileageEvidenceAdmin(admin.ModelAdmin):
    """Evidence is managed through the transactional Office workflow only."""
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


for mileage_model in (MileageLedger, MileageJourney, MileageClaim, MileageClaimLine):
    admin.site.register(mileage_model, MileageEvidenceAdmin)
