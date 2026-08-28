from django.test import TestCase


class ContactPageTests(TestCase):
    def test_contact_page_loads(self):
        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'GET IN TOUCH NOW!')
