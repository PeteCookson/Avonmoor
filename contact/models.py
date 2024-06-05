from django.db import models

class Contact(models.Model):
    SUBJECT_CHOICES = [
        ('Garden', 'Garden'),
        ('Property', 'Property'),
        ('Combination', 'Combination'),
        ('Other', 'Other'),
    ]

    name = models.CharField(max_length=255, null=True, blank=True)  # Default name
    email = models.EmailField()  # Email field
    phone_number = models.CharField(max_length=20, null=True, blank=True)  # Default phone number
    postcode = models.CharField(max_length=20, null=True, blank=True)
    subject = models.CharField(max_length=255, choices=SUBJECT_CHOICES)  # Subject field with choices
    message = models.TextField()  # Message field

    def __str__(self):
        return f"{self.name} - {self.email}"  # Adjusted to display name and email

