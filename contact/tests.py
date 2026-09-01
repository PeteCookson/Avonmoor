from unittest.mock import patch

from django.test import TestCase

from .forms import ContactForm
from .models import Contact


class ContactPageTests(TestCase):
    def test_homepage_presents_both_service_routes(self):
        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Garden &amp; Property Maintenance')
        self.assertContains(response, 'Rainwater Harvesting')
        self.assertContains(response, '/garden-property-maintenance/')
        self.assertContains(response, '/rainwater-harvesting/')
        self.assertContains(response, 'avonmoor-master-horizontal-light.svg')

    def test_footer_preserves_all_socials_and_roman_year(self):
        response = self.client.get('/')

        for social in ('Facebook', 'Instagram', 'YouTube', 'TikTok'):
            self.assertContains(response, social)
        self.assertContains(response, '© AVONMOOR MMXXVI')

    def test_rainwater_page_links_to_calculator(self):
        response = self.client.get('/rainwater-harvesting/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '/rainwater-calculator/')

    def test_garden_property_page_loads(self):
        response = self.client.get('/garden-property-maintenance/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Look after the place you live.')
        self.assertContains(response, 'South Brent')
        self.assertNotContains(response, 'Non-gas')

    def test_contact_page_loads(self):
        response = self.client.get('/contact/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Tell us what you need.')
        self.assertNotContains(response, 'South Brent')
        self.assertContains(response, 'css/contact.css?v=20260901-2')

    @patch('contact.views.send_mail', side_effect=OSError('SMTP unavailable'))
    def test_contact_submission_survives_email_outage(self, _send_mail):
        response = self.client.post('/contact/', data={
            'name': 'Test Customer',
            'email': 'customer@example.com',
            'phone_number': '07123 456 789',
            'postcode': 'TQ10 9AB',
            'subject': 'Rainwater Harvesting',
            'message': 'Please contact me about a rainwater system.',
        })

        self.assertRedirects(response, '/contact/?success=1')
        self.assertEqual(Contact.objects.count(), 1)

        success_response = self.client.get(response.url)
        self.assertContains(success_response, 'your enquiry has been received')

    def test_contact_subjects_are_separate_and_include_rainwater(self):
        form = ContactForm()
        choices = [value for value, _label in form.fields['subject'].choices]

        self.assertEqual(
            choices,
            ['', 'Garden', 'Property', 'Rainwater Harvesting', 'Other'],
        )

    def test_rainwater_subject_is_valid(self):
        form = ContactForm(data={
            'name': 'Test Customer',
            'email': 'customer@example.com',
            'phone_number': '07123 456 789',
            'postcode': 'TQ10 9AB',
            'subject': 'Rainwater Harvesting',
            'message': 'Please contact me about a rainwater system.',
        })

        self.assertTrue(form.is_valid(), form.errors)

    def test_contact_page_can_preselect_service(self):
        response = self.client.get('/contact/?service=rainwater')

        self.assertEqual(
            response.context['form']['subject'].value(),
            'Rainwater Harvesting',
        )

    def test_privacy_notice_explains_calculator_and_postcode_fallback(self):
        response = self.client.get('/privacy/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Company Information &amp; Privacy')
        self.assertContains(response, 'Company number 04655485')
        self.assertContains(response, 'Victoria Cottage')
        self.assertContains(response, 'Avonmoor Ltd, company number 04655485, is the data controller')
        self.assertContains(response, 'held in an essential website session for up to one hour')
        self.assertContains(response, 'Postcodes.io')
        self.assertContains(response, 'No automated mailing list')

    def test_site_footer_links_to_privacy_notice(self):
        response = self.client.get('/')

        self.assertContains(response, 'href="/privacy/"')
