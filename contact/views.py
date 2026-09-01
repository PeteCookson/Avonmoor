import logging

from django.shortcuts import render, redirect
from django.http import HttpResponseRedirect
from django.urls import reverse

from avonmoor.email_notifications import send_branded_notification

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
            enquiry = form.save()
            service = form.cleaned_data['subject']
            if service == 'Rainwater Harvesting':
                notification_type = 'rainwater'
                subject_label = 'RAINWATER'
            elif service in {'Garden', 'Property'}:
                notification_type = 'garden'
                subject_label = 'GARDEN & PROPERTY'
            else:
                notification_type = 'other'
                subject_label = 'GENERAL'

            subject = (
                f'{subject_label} ENQUIRY — {service} — '
                f'{enquiry.postcode} — {enquiry.name}'
            )
            from_email = 'hello@avonmoor.co.uk'
            recipient_list = ['hello@avonmoor.co.uk']
            try:
                send_branded_notification(
                    subject=subject,
                    heading=f'New {service} Enquiry',
                    notification_type=notification_type,
                    message=enquiry.message,
                    fields=[
                        ('Name', enquiry.name),
                        ('Email', enquiry.email),
                        ('Phone', enquiry.phone_number),
                        ('Postcode', enquiry.postcode),
                        ('Service requested', service),
                    ],
                    reply_to=enquiry.email,
                    from_email=from_email,
                    recipient_list=recipient_list,
                )
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
