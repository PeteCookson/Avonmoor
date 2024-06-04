from django.forms import ModelForm
from .models import Contact
from django.core.validators import EmailValidator


class ContactForm(ModelForm):
    class Meta:
        model = Contact
        fields = '__all__'