from django.contrib import admin
from django.utils import timezone
from .models import Contact
from .forms import ContactForm

class ContactAdmin(admin.ModelAdmin):
    form = ContactForm
    list_display = ('name', 'email', 'phone_number', 'postcode', 'subject', 'formatted_created_at')
    readonly_fields = ('created_at',)

    def save_model(self, request, obj, form, change):
        if obj.postcode:
            obj.postcode = obj.postcode.replace(" ", "").upper()
        super().save_model(request, obj, form, change)

    def formatted_created_at(self, obj):
        # Use the created_at_local method to get the local time and format it
        local_created_at = obj.created_at_local()
        return local_created_at.strftime('%H:%M, %d %B %Y')
    
    formatted_created_at.short_description = 'Created At'

admin.site.register(Contact, ContactAdmin)
