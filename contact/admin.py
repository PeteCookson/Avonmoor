from django.contrib import admin
from .models import Contact
from .forms import ContactForm

class ContactAdmin(admin.ModelAdmin):
    form = ContactForm

    def save_model(self, request, obj, form, change):
        if obj.postcode:
            obj.postcode = obj.postcode.replace(" ", "").upper()
        super().save_model(request, obj, form, change)

admin.site.register(Contact, ContactAdmin)
