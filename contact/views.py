from django.core.mail import send_mail
from django.shortcuts import render
from django.http import HttpResponseRedirect
from django.urls import reverse
from .forms import ContactForm

def contact_view(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            form.save()

            # Send email
            # subject = 'New Contact Form Submission'
            # message = f'Name: {form.cleaned_data["name"]}\nEmail: {form.cleaned_data["email"]}\nPhone Number: {form.cleaned_data["phone_number"]}\nPostcode: {form.cleaned_data["postcode"]}\nSubject: {form.cleaned_data["subject"]}\nMessage: {form.cleaned_data["message"]}'
            # from_email = 'hello@avonmoor.co.uk'
            # recipient_list = ['hello@avonmoor.co.uk']
            # send_mail(subject, message, from_email, recipient_list)

            return render(request, 'contact.html', {'form': ContactForm(), 'success': True})
    else:
        form = ContactForm()
    return render(request, 'contact.html', {'form': form})

