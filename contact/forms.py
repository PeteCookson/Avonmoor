from django import forms
from django.core.validators import EmailValidator, MinLengthValidator
from django.core.exceptions import ValidationError
from .constants import VALID_POSTCODES
from .models import Contact

def validate_postcode(value):
    normalized_value = value.replace(" ", "").upper()  # Remove spaces and convert to uppercase
    if normalized_value not in VALID_POSTCODES:
        raise ValidationError('Invalid postcode')

class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = ['name', 'email', 'phone_number', 'postcode', 'subject', 'message']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Name', 'class': 'form-control name-field'}),
            'email': forms.EmailInput(attrs={'placeholder': 'Email', 'class': 'form-control email-field'}),
            'phone_number': forms.TextInput(attrs={'placeholder': 'Phone', 'class': 'form-control phone-field'}),
            'postcode': forms.TextInput(attrs={'placeholder': 'Postcode', 'class': 'form-control postcode-field'}),
            'subject': forms.Select(attrs={'class': 'form-control subject-field'}, choices=[
                ('', 'Enquiry Subject'),
                ('Garden', 'Garden'),
                ('Property', 'Property'),
                ('Garden & Property', 'Garden & Property'),
                ('Other', 'Other')
            ]),
            'message': forms.Textarea(attrs={'placeholder': 'Message', 'class': 'form-control message-field'}),
        }

    def clean_postcode(self):
        postcode = self.cleaned_data['postcode']
        normalized_postcode = postcode.replace(" ", "").upper()
        validate_postcode(normalized_postcode)  # Validate normalized postcode
        return normalized_postcode

    def clean_email(self):
        email = self.cleaned_data['email']
        validator = EmailValidator()
        validator(email)  # Raises ValidationError if email is not valid
        return email

    def clean_phone_number(self):
        phone_number = self.cleaned_data['phone_number']
        return phone_number

    def clean_subject(self):
        subject = self.cleaned_data['subject']
        if not subject:
            raise forms.ValidationError("Please select a subject.")
        return subject

    def clean_message(self):
        message = self.cleaned_data['message']
        validator = MinLengthValidator(10)  # Minimum 10 characters for message
        validator(message)  # Raises ValidationError if message length is less than 10
        return message
