import re
from django import forms
from django.core.validators import EmailValidator, MinLengthValidator
from django.core.exceptions import ValidationError
from .constants import VALID_POSTCODES
from .models import Contact

POSTCODE_REGEX = re.compile(r'^[A-Z]{2}\d{2,}[A-Z]{2}$')
UK_PHONE_REGEX = re.compile(r'^(\+44\s?7\d{3}|\(?07\d{3}\)?)\s?\d{3}\s?\d{3}$|^(\+44\s?1\d{3}|\(?01\d{3}\)?)\s?\d{3}\s?\d{3}$|^(\+44\s?2\d{3}|\(?02\d{3}\)?)\s?\d{3}\s?\d{3}$')
LOCAL_SERVICE_OUTCODES = frozenset({'PL21', 'TQ10', 'TQ11'})
LOCAL_SERVICE_SUBJECTS = frozenset({'Garden', 'Property', 'Other'})


def validate_postcode(value):
    normalized_value = value.replace(" ", "").upper()  # Remove spaces and convert to uppercase
    if not POSTCODE_REGEX.match(normalized_value):  # Check if the postcode matches the pattern
        raise ValidationError('Please enter a valid postcode')
    if normalized_value not in VALID_POSTCODES:  # Check if the postcode is not covered
        raise ValidationError('Sorry, we do not currently cover this postcode.')

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
                ('Rainwater Harvesting', 'Rainwater Harvesting'),
                ('Other', 'Other')
            ]),
            'message': forms.Textarea(attrs={'placeholder': 'Message', 'class': 'form-control message-field'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Postcode is required to enforce Avonmoor's service area. Email is
        # already required, so phone can remain optional without losing a
        # reliable reply route.
        self.fields['postcode'].required = True
        self.fields['phone_number'].required = False
        self.fields['postcode'].help_text = (
            'Garden, Property and Other enquiries: TQ10, TQ11 and PL21. '
            'Rainwater Harvesting: wider South Devon.'
        )

    def clean_postcode(self):
        postcode = self.cleaned_data.get('postcode')
        if not postcode:
            raise ValidationError('Please enter your postcode.')
        normalized_postcode = postcode.replace(" ", "").upper()
        validate_postcode(normalized_postcode)  # Validate normalized postcode
        return normalized_postcode

    def clean_email(self):
        email = self.cleaned_data['email']
        validator = EmailValidator()
        validator(email)  # Raises ValidationError if email is not valid
        return email

    def clean_phone_number(self):
        phone_number = self.cleaned_data.get('phone_number')
        if phone_number and not UK_PHONE_REGEX.match(phone_number):
            raise ValidationError('Please enter a valid UK phone number')
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

    def clean(self):
        cleaned_data = super().clean()
        postcode = cleaned_data.get('postcode')
        subject = cleaned_data.get('subject')

        if (
            postcode
            and subject in LOCAL_SERVICE_SUBJECTS
            and postcode[:-3] not in LOCAL_SERVICE_OUTCODES
        ):
            self.add_error(
                'postcode',
                'For this enquiry type, Avonmoor currently covers TQ10, '
                'TQ11 and PL21.',
            )

        return cleaned_data
