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
        self.assertContains(response, 'css/contact.css?v=20260901-5')
        self.assertContains(
            response,
            'Garden, Property and Other enquiries: TQ10, TQ11 and PL21.',
        )

    @patch('contact.views.send_mail', side_effect=OSError('SMTP unavailable'))
    def test_contact_submission_survives_email_outage(self, _send_mail):
        response = self.client.post('/contact/', data={
            'name': 'Test Customer',
            'email': 'customer@example.com',
            'phone_number': '',
            'postcode': 'TQ10 9AB',
            'subject': 'Rainwater Harvesting',
            'message': 'Please contact me about a rainwater system.',
        })

        self.assertRedirects(response, '/contact/?success=1')
        self.assertEqual(Contact.objects.count(), 1)

        success_response = self.client.get(response.url)
        self.assertContains(success_response, 'your enquiry has been received')

    def test_postcode_is_required_and_phone_is_optional(self):
        form = ContactForm(data={
            'name': 'Test Customer',
            'email': 'customer@example.com',
            'phone_number': '',
            'postcode': 'TQ10 9AB',
            'subject': 'Garden',
            'message': 'Please contact me about some garden work.',
        })

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.fields['postcode'].required)
        self.assertFalse(form.fields['phone_number'].required)

    def test_blank_postcode_is_rejected_without_server_error(self):
        form = ContactForm(data={
            'name': 'Test Customer',
            'email': 'customer@example.com',
            'phone_number': '',
            'postcode': '',
            'subject': 'Garden',
            'message': 'Please contact me about some garden work.',
        })

        self.assertFalse(form.is_valid())
        self.assertIn('postcode', form.errors)

    def test_invalid_phone_is_rejected_when_supplied(self):
        form = ContactForm(data={
            'name': 'Test Customer',
            'email': 'customer@example.com',
            'phone_number': '12345',
            'postcode': 'TQ10 9AB',
            'subject': 'Garden',
            'message': 'Please contact me about some garden work.',
        })

        self.assertFalse(form.is_valid())
        self.assertIn('phone_number', form.errors)

    def test_local_services_accept_only_local_postcode_districts(self):
        for postcode in ('TQ10 9AB', 'TQ11 0NA', 'PL21 0PF'):
            with self.subTest(postcode=postcode):
                form = ContactForm(data={
                    'name': 'Test Customer',
                    'email': 'customer@example.com',
                    'phone_number': '',
                    'postcode': postcode,
                    'subject': 'Garden',
                    'message': 'Please contact me about some garden work.',
                })

                self.assertTrue(form.is_valid(), form.errors)

    def test_broad_postcode_is_rejected_for_local_services(self):
        for subject in ('Garden', 'Property', 'Other'):
            with self.subTest(subject=subject):
                form = ContactForm(data={
                    'name': 'Test Customer',
                    'email': 'customer@example.com',
                    'phone_number': '',
                    'postcode': 'TQ2 7JH',
                    'subject': subject,
                    'message': 'Please contact me about this service enquiry.',
                })

                self.assertFalse(form.is_valid())
                self.assertIn('postcode', form.errors)

    def test_rainwater_enquiry_retains_broad_postcode_coverage(self):
        for postcode in ('TQ1 1AG', 'TQ2 7JH'):
            with self.subTest(postcode=postcode):
                form = ContactForm(data={
                    'name': 'Test Customer',
                    'email': 'customer@example.com',
                    'phone_number': '',
                    'postcode': postcode,
                    'subject': 'Rainwater Harvesting',
                    'message': 'Please contact me about a rainwater system.',
                })

                self.assertTrue(form.is_valid(), form.errors)

    def test_rainwater_enquiry_rejects_postcodes_outside_broad_area(self):
        form = ContactForm(data={
            'name': 'Test Customer',
            'email': 'customer@example.com',
            'phone_number': '',
            'postcode': 'EX1 1AA',
            'subject': 'Rainwater Harvesting',
            'message': 'Please contact me about a rainwater system.',
        })

        self.assertFalse(form.is_valid())
        self.assertIn('postcode', form.errors)

    def test_torquay_postcode_is_still_rejected_for_garden_work(self):
        form = ContactForm(data={
            'name': 'Test Customer',
            'email': 'customer@example.com',
            'phone_number': '',
            'postcode': 'TQ1 1AG',
            'subject': 'Garden',
            'message': 'Please contact me about some garden work.',
        })

        self.assertFalse(form.is_valid())
        self.assertIn('postcode', form.errors)

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
        self.assertContains(response, 'linked to the resulting survey')
        self.assertContains(response, 'No automated mailing list')

    def test_site_footer_links_to_privacy_notice(self):
        response = self.client.get('/')

        self.assertContains(response, 'href="/privacy/"')
