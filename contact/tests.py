from django.test import TestCase

from .forms import ContactForm


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
