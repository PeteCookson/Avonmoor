import logging

from django.core.mail import send_mail
from django.shortcuts import render, redirect
from django.http import HttpResponseRedirect
from django.urls import reverse
from .forms import ContactForm


logger = logging.getLogger(__name__)


def home_view(request):
    return render(request, 'home.html')


def garden_property_view(request):
    return render(request, 'garden_property.html')


def rainwater_harvesting_view(request):
    return render(request, 'rainwater_harvesting.html')


def privacy_view(request):
    return render(request, 'privacy.html')


def contact_view(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            form.save()

            # Send email (example, replace with your own logic)
            subject = 'New Contact Form Submission'
            message = f'Name: {form.cleaned_data["name"]}\nEmail: {form.cleaned_data["email"]}\nPhone Number: {form.cleaned_data["phone_number"]}\nPostcode: {form.cleaned_data["postcode"]}\nSubject: {form.cleaned_data["subject"]}\nMessage: {form.cleaned_data["message"]}'
            from_email = 'hello@avonmoor.co.uk'
            recipient_list = ['hello@avonmoor.co.uk']
            try:
                send_mail(subject, message, from_email, recipient_list)
            except Exception:
                # The enquiry is already safely stored in the database. An
                # email-provider outage must not lose it or expose a 500 page
                # to the customer; retain the traceback in the server log.
                logger.exception('Contact notification email could not be sent')

            # Redirect to the same page with success parameter
            return HttpResponseRedirect(reverse('contact') + '?success=1')
    else:
        initial_subjects = {
            'garden': 'Garden',
            'property': 'Property',
            'rainwater': 'Rainwater Harvesting',
        }
        form = ContactForm(
            initial={'subject': initial_subjects.get(request.GET.get('service'))}
        )

    success = request.GET.get('success', False)

    return render(request, 'contact.html', {'form': form, 'success': success})
