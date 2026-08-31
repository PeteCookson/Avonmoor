from django.test import TestCase


class ContactPageTests(TestCase):
    def test_homepage_presents_both_service_routes(self):
        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Garden &amp; Property Maintenance')
        self.assertContains(response, 'Rainwater Harvesting')
        self.assertContains(response, '/garden-property-maintenance/')
        self.assertContains(response, '/rainwater-harvesting/')

    def test_rainwater_page_links_to_calculator(self):
        response = self.client.get('/rainwater-harvesting/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '/rainwater-calculator/')

    def test_garden_property_page_loads(self):
        response = self.client.get('/garden-property-maintenance/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Look after the place you live.')

    def test_contact_page_loads(self):
        response = self.client.get('/contact/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Tell us what you need.')

    def test_contact_page_can_preselect_service(self):
        response = self.client.get('/contact/?service=rainwater')

        self.assertEqual(
            response.context['form']['subject'].value(),
            'Rainwater Harvesting',
        )
