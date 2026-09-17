from django.core import mail
from django.test import TestCase, override_settings


class ContactNotificationRecipientTests(TestCase):
    @override_settings(
        NOTIFICATION_RECIPIENTS=[
            'hello@example.com',
            'owner@example.com',
        ]
    )
    def test_contact_enquiry_reaches_primary_and_backup_inboxes(self):
        self.client.post('/contact/', data={
            'name': 'Test Customer',
            'email': 'customer@example.com',
            'phone_number': '',
            'postcode': 'TQ10 9AB',
            'subject': 'Rainwater Harvesting',
            'message': 'Please assess the house for a rainwater system.',
        })

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].to,
            ['hello@example.com', 'owner@example.com'],
        )
