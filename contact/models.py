from django.db import models

class Contact(models.Model):
    SUBJECT_CHOICES = [
        ('Garden', 'Garden'),
        ('Property', 'Property'),
        ('Garden & Property', 'Garden & Property'),
        ('Other', 'Other'),
    ]

    name = models.CharField(max_length=255, null=True, blank=True)
    email = models.EmailField()
    phone_number = models.CharField(max_length=20, null=True, blank=True)
    postcode = models.CharField(max_length=20, null=True, blank=True)
    subject = models.CharField(max_length=255, choices=SUBJECT_CHOICES)
    message = models.TextField()

    def __str__(self):
        return f"{self.name} - {self.email}"

    def save(self, *args, **kwargs):
        if self.postcode:
            self.postcode = self.postcode.replace(" ", "").upper()
        super().save(*args, **kwargs)