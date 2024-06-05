from django import forms
from django.core.validators import MinLengthValidator, EmailValidator, RegexValidator
from .models import Contact

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
                ('', 'Select the service'),  # Placeholder choice
                ('Garden', 'Garden'),
                ('Property', 'Property'),
                ('Combination', 'Combination'),
                ('Other', 'Other')
            ]),
            'message': forms.Textarea(attrs={'placeholder': 'Message', 'class': 'form-control message-field'}),
        }

    def clean_email(self):
        email = self.cleaned_data['email']
        validator = EmailValidator()
        validator(email)  # Raises ValidationError if email is not valid
        return email

    def clean_phone_number(self):
        phone_number = self.cleaned_data['phone_number']
        # Add any custom phone number validation here if needed
        return phone_number

    def clean_postcode(self):
        postcode = self.cleaned_data['postcode']
        # Add any custom postcode validation here if needed
        return postcode

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






