from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import Customer, Invoice, InvoiceLine, Property, WorkEntry


class OfficeFixtureMixin:
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username='pete', password='test-password', is_staff=True
        )
        self.accountant = get_user_model().objects.create_user(
            username='accountant', password='test-password', is_staff=True
        )
        self.ordinary_user = get_user_model().objects.create_user(
            username='visitor', password='test-password'
        )
        self.customer = Customer.objects.create(
            display_name='Test Customer',
            contact_name='Alex Test',
            email='alex@example.com',
            billing_address_1='1 Test Lane',
            town='South Brent',
            postcode='TQ10 9AA',
        )
        self.property = Property.objects.create(
            customer=self.customer,
            name='Test Garden',
            address_line_1='1 Test Lane',
            town='South Brent',
            postcode='TQ10 9AA',
        )
        self.work = WorkEntry.objects.create(
            property=self.property,
            service_date=date(2026, 11, 1),
            category=WorkEntry.Category.LABOUR,
            description='Garden maintenance',
            quantity=Decimal('2.00'),
            unit=WorkEntry.Unit.HOURS,
            unit_price=Decimal('25.00'),
            created_by=self.staff,
        )

    def make_invoice(self, issue_date=date(2026, 11, 2)):
        invoice = Invoice.objects.create(
            customer=self.customer,
            property=self.property,
            issue_date=issue_date,
            created_by=self.staff,
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            work_entry=self.work,
            service_date=self.work.service_date,
            category=self.work.category,
            description=self.work.description,
            quantity=self.work.quantity,
            unit=self.work.unit,
            unit_price=self.work.unit_price,
        )
        return invoice


class OfficeAccessTests(OfficeFixtureMixin, TestCase):
    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse('office:dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_non_staff_user_is_forbidden(self):
        self.client.force_login(self.ordinary_user)
        response = self.client.get(reverse('office:dashboard'))
        self.assertEqual(response.status_code, 403)

    def test_staff_user_and_accountant_can_access(self):
        for user in (self.staff, self.accountant):
            self.client.force_login(user)
            response = self.client.get(reverse('office:dashboard'))
            self.assertEqual(response.status_code, 200)

    def test_staff_can_open_all_stage_one_pages(self):
        self.client.force_login(self.staff)
        urls = [
            reverse('office:customer-list'),
            reverse('office:customer-create'),
            reverse('office:customer-detail', args=[self.customer.pk]),
            reverse('office:property-create', args=[self.customer.pk]),
            reverse('office:property-edit', args=[self.property.pk]),
            reverse('office:work-list'),
            reverse('office:work-create'),
            reverse('office:work-edit', args=[self.work.pk]),
            reverse('office:invoice-list'),
            reverse('office:invoice-create'),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)


class InvoiceModelTests(OfficeFixtureMixin, TestCase):
    def test_issue_assigns_sequential_number_and_freezes_customer(self):
        invoice = self.make_invoice()
        issued = invoice.issue()
        self.assertEqual(issued.number, 'INV-2026-001')
        self.assertEqual(issued.status, Invoice.Status.ISSUED)
        self.assertEqual(issued.total, Decimal('50.00'))
        self.assertEqual(issued.customer_snapshot['display_name'], 'Test Customer')

        self.customer.display_name = 'Changed Later'
        self.customer.save()
        issued.refresh_from_db()
        self.assertEqual(issued.billing_details['display_name'], 'Test Customer')

    def test_sequences_restart_each_year(self):
        first = self.make_invoice(date(2026, 12, 31)).issue()
        second_work = WorkEntry.objects.create(
            property=self.property,
            service_date=date(2027, 1, 2),
            description='Winter pruning',
            quantity=Decimal('1.00'),
            unit_price=Decimal('30.00'),
            created_by=self.staff,
        )
        second = Invoice.objects.create(
            customer=self.customer,
            property=self.property,
            issue_date=date(2027, 1, 3),
            created_by=self.staff,
        )
        InvoiceLine.objects.create(
            invoice=second,
            work_entry=second_work,
            service_date=second_work.service_date,
            description=second_work.description,
            quantity=second_work.quantity,
            unit=second_work.unit,
            unit_price=second_work.unit_price,
        )
        second = second.issue()
        self.assertEqual(first.number, 'INV-2026-001')
        self.assertEqual(second.number, 'INV-2027-001')

    def test_invoice_requires_line_before_issue(self):
        invoice = Invoice.objects.create(
            customer=self.customer,
            issue_date=date(2026, 11, 2),
            created_by=self.staff,
        )
        with self.assertRaises(ValidationError):
            invoice.issue()

    def test_property_must_belong_to_customer(self):
        other = Customer.objects.create(
            display_name='Other Customer',
            billing_address_1='2 Other Road',
            postcode='TQ10 9BB',
        )
        invoice = Invoice(
            customer=other,
            property=self.property,
            created_by=self.staff,
        )
        with self.assertRaises(ValidationError):
            invoice.full_clean()


class InvoiceWorkflowTests(OfficeFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.staff)

    def test_create_invoice_from_work_entry(self):
        response = self.client.post(
            reverse('office:invoice-create'),
            {
                'customer': self.customer.pk,
                'property': self.property.pk,
                'issue_date': '2026-11-02',
                'work_entries': [self.work.pk],
            },
        )
        self.assertEqual(response.status_code, 302)
        invoice = Invoice.objects.get()
        self.assertEqual(invoice.lines.count(), 1)
        self.assertEqual(invoice.total, Decimal('50.00'))
        self.assertTrue(self.work.is_invoiced)

    def test_issue_and_download_branded_pdf(self):
        invoice = self.make_invoice()
        issue_response = self.client.post(
            reverse('office:invoice-issue', args=[invoice.pk])
        )
        self.assertRedirects(
            issue_response, reverse('office:invoice-detail', args=[invoice.pk])
        )
        invoice.refresh_from_db()

        response = self.client.get(
            reverse('office:invoice-pdf', args=[invoice.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('INV-2026-001.pdf', response['Content-Disposition'])
        self.assertTrue(response.content.startswith(b'%PDF'))
        self.assertGreater(len(response.content), 5000)

    def test_draft_pdf_download_is_blocked(self):
        invoice = self.make_invoice()
        response = self.client.get(
            reverse('office:invoice-pdf', args=[invoice.pk])
        )
        self.assertRedirects(
            response, reverse('office:invoice-edit', args=[invoice.pk])
        )

    def test_mark_paid_preserves_invoice(self):
        invoice = self.make_invoice().issue()
        response = self.client.post(
            reverse('office:invoice-paid', args=[invoice.pk])
        )
        self.assertEqual(response.status_code, 302)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.PAID)
        self.assertIsNotNone(invoice.paid_at)

    def test_accountant_csv_exports(self):
        invoice = self.make_invoice().issue()
        customer_export = self.client.get(reverse('office:customer-export'))
        self.assertEqual(customer_export.status_code, 200)
        self.assertEqual(customer_export['Content-Type'], 'text/csv')
        self.assertIn(b'Test Customer', customer_export.content)

        invoice_export = self.client.get(reverse('office:invoice-export'))
        self.assertEqual(invoice_export.status_code, 200)
        self.assertEqual(invoice_export['Content-Type'], 'text/csv')
        self.assertIn(invoice.number.encode(), invoice_export.content)
        self.assertIn(b'50.00', invoice_export.content)
