from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core import mail
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse

from .forms import InvoiceForm
from .models import (
    BusinessBranch,
    Customer,
    Expense,
    Invoice,
    InvoiceEmail,
    InvoiceLine,
    Property,
    WorkEntry,
)
from .mailbox import append_message_to_sent
from .views import available_work_entries_for_update


class OfficeFixtureMixin:
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username='pete',
            password='test-password',
            is_staff=True,
            is_superuser=True,
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

    def test_office_home_separates_both_business_branches(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('office:dashboard'))
        self.assertContains(response, 'Garden &amp; Property')
        self.assertContains(response, 'Rainwater Harvesting')
        self.assertContains(
            response,
            reverse('office:branch-dashboard', args=[BusinessBranch.GARDEN]),
        )
        self.assertContains(
            response,
            reverse('office:branch-dashboard', args=[BusinessBranch.RAINWATER]),
        )

    def test_surveys_navigation_only_appears_in_rainwater_branch(self):
        self.client.force_login(self.staff)
        surveys_url = reverse('water_survey:survey-list')

        office_home = self.client.get(reverse('office:dashboard'))
        garden = self.client.get(
            reverse(
                'office:branch-dashboard', args=[BusinessBranch.GARDEN]
            )
        )
        rainwater = self.client.get(
            reverse(
                'office:branch-dashboard', args=[BusinessBranch.RAINWATER]
            )
        )

        self.assertNotContains(office_home, f'href="{surveys_url}"')
        self.assertNotContains(garden, f'href="{surveys_url}"')
        self.assertContains(rainwater, f'href="{surveys_url}"')

    def test_branch_navigation_is_grouped_by_task(self):
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse('office:branch-dashboard', args=[BusinessBranch.GARDEN])
        )

        self.assertContains(response, '<summary>Work</summary>', html=True)
        self.assertContains(response, '<summary>Billing</summary>', html=True)
        self.assertContains(response, '<summary>Accounts</summary>', html=True)
        self.assertContains(response, 'People and properties')
        self.assertContains(response, 'Create, send and track invoices')
        self.assertContains(response, 'Review Monzo spending')
        self.assertContains(response, 'Journeys and reimbursement claims')
        self.assertContains(response, 'Switch branch')

    def test_global_accounts_pages_keep_navigation_grouped(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('office:accounting'))

        self.assertContains(response, '<summary>Accounts</summary>', html=True)
        self.assertContains(response, 'Review Monzo spending')
        self.assertContains(response, 'Match customer payments')
        self.assertContains(response, 'Choose branch')

    def test_staff_login_without_next_redirects_to_office(self):
        response = self.client.post(
            reverse('login'),
            {'username': 'accountant', 'password': 'test-password'},
        )
        self.assertRedirects(response, reverse('office:dashboard'))

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


class PropertyWorkflowTests(OfficeFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.staff)

    def test_property_can_copy_customer_billing_address(self):
        response = self.client.post(
            reverse('office:property-create', args=[self.customer.pk]),
            {
                'same_as_billing': 'on',
                'name': 'Billing address property',
                'address_line_1': '',
                'address_line_2': '',
                'town': '',
                'county': '',
                'postcode': '',
                'active': 'on',
            },
        )
        self.assertEqual(response.status_code, 302)
        property_record = Property.objects.get(name='Billing address property')
        self.assertEqual(property_record.address_line_1, self.customer.billing_address_1)
        self.assertEqual(property_record.town, self.customer.town)
        self.assertEqual(property_record.postcode, self.customer.postcode)

    def test_unused_property_can_be_deleted(self):
        unused = Property.objects.create(
            customer=self.customer,
            name='Unused',
            address_line_1='2 Test Lane',
            postcode='TQ10 9AB',
        )
        response = self.client.post(
            reverse('office:property-delete', args=[unused.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Property.objects.filter(pk=unused.pk).exists())

    def test_property_with_history_cannot_be_deleted(self):
        response = self.client.post(
            reverse('office:property-delete', args=[self.property.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Property.objects.filter(pk=self.property.pk).exists())

    def test_accountant_cannot_delete_property(self):
        unused = Property.objects.create(
            customer=self.customer,
            name='Accountant must not delete this',
            address_line_1='3 Test Lane',
            postcode='TQ10 9AC',
        )
        self.client.force_login(self.accountant)
        response = self.client.post(
            reverse('office:property-delete', args=[unused.pk])
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Property.objects.filter(pk=unused.pk).exists())

    def test_accountant_does_not_see_property_delete_action(self):
        self.client.force_login(self.accountant)
        response = self.client.get(
            reverse('office:customer-detail', args=[self.customer.pk])
        )
        self.assertNotContains(response, 'Delete')

    def test_customer_registers_are_separate(self):
        rainwater_customer = Customer.objects.create(
            branch=BusinessBranch.RAINWATER,
            display_name='Rainwater Only',
            billing_address_1='2 Water Lane',
            postcode='TQ10 9RW',
        )
        garden_response = self.client.get(
            reverse('office:customer-list', args=[BusinessBranch.GARDEN])
        )
        rainwater_response = self.client.get(
            reverse('office:customer-list', args=[BusinessBranch.RAINWATER])
        )
        self.assertContains(garden_response, self.customer.display_name)
        self.assertNotContains(garden_response, rainwater_customer.display_name)
        self.assertContains(rainwater_response, rainwater_customer.display_name)
        self.assertNotContains(rainwater_response, self.customer.display_name)


class ExpenseWorkflowTests(OfficeFixtureMixin, TestCase):
    def expense_data(self, **overrides):
        data = {
            'expense_date': '2026-11-07',
            'supplier': 'Devon Garden Supplies',
            'category': Expense.Category.MATERIALS,
            'description': 'Compost and stakes',
            'property': self.property.pk,
            'amount': '42.50',
            'payment_method': Expense.PaymentMethod.CARD,
            'reference': 'RCPT-1042',
            'notes': 'For autumn maintenance',
        }
        data.update(overrides)
        return data

    def make_expense(self, **overrides):
        values = {
            'branch': BusinessBranch.GARDEN,
            'expense_date': date(2026, 11, 7),
            'supplier': 'Devon Garden Supplies',
            'category': Expense.Category.MATERIALS,
            'description': 'Compost and stakes',
            'property': self.property,
            'amount': Decimal('42.50'),
            'payment_method': Expense.PaymentMethod.CARD,
            'reference': 'RCPT-1042',
            'created_by': self.staff,
            'updated_by': self.staff,
        }
        values.update(overrides)
        return Expense.objects.create(**values)

    def test_accountant_can_record_and_edit_expense(self):
        self.client.force_login(self.accountant)
        response = self.client.post(
            reverse('office:expense-create', args=[BusinessBranch.GARDEN]),
            self.expense_data(),
        )
        self.assertRedirects(
            response,
            reverse('office:expense-list', args=[BusinessBranch.GARDEN]),
        )
        expense = Expense.objects.get()
        self.assertEqual(expense.created_by, self.accountant)
        self.assertEqual(expense.branch, BusinessBranch.GARDEN)

        response = self.client.post(
            reverse(
                'office:expense-edit',
                args=[BusinessBranch.GARDEN, expense.pk],
            ),
            self.expense_data(amount='45.00'),
        )
        self.assertEqual(response.status_code, 302)
        expense.refresh_from_db()
        self.assertEqual(expense.amount, Decimal('45.00'))
        self.assertEqual(expense.updated_by, self.accountant)

    def test_expense_register_is_separate_by_branch(self):
        garden_expense = self.make_expense()
        rainwater_customer = Customer.objects.create(
            branch=BusinessBranch.RAINWATER,
            display_name='Rainwater Customer',
            billing_address_1='2 Water Lane',
            postcode='TQ10 9RW',
        )
        rainwater_property = Property.objects.create(
            customer=rainwater_customer,
            name='Tank site',
            address_line_1='2 Water Lane',
            postcode='TQ10 9RW',
        )
        rainwater_expense = self.make_expense(
            branch=BusinessBranch.RAINWATER,
            supplier='Tank Supplier',
            property=rainwater_property,
        )
        self.client.force_login(self.staff)

        garden = self.client.get(
            reverse('office:expense-list', args=[BusinessBranch.GARDEN])
        )
        rainwater = self.client.get(
            reverse('office:expense-list', args=[BusinessBranch.RAINWATER])
        )
        self.assertContains(garden, garden_expense.supplier)
        self.assertNotContains(garden, rainwater_expense.supplier)
        self.assertContains(rainwater, rainwater_expense.supplier)
        self.assertNotContains(rainwater, garden_expense.supplier)

    def test_cross_branch_property_is_rejected(self):
        rainwater_customer = Customer.objects.create(
            branch=BusinessBranch.RAINWATER,
            display_name='Rainwater Customer',
            billing_address_1='2 Water Lane',
            postcode='TQ10 9RW',
        )
        rainwater_property = Property.objects.create(
            customer=rainwater_customer,
            address_line_1='2 Water Lane',
            postcode='TQ10 9RW',
        )
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse('office:expense-create', args=[BusinessBranch.GARDEN]),
            self.expense_data(property=rainwater_property.pk),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Expense.objects.exists())

    def test_accountant_cannot_void_expense(self):
        expense = self.make_expense()
        self.client.force_login(self.accountant)
        response = self.client.post(
            reverse(
                'office:expense-void',
                args=[BusinessBranch.GARDEN, expense.pk],
            )
        )
        self.assertEqual(response.status_code, 403)
        expense.refresh_from_db()
        self.assertIsNone(expense.voided_at)

    def test_owner_voids_without_deleting_audit_record(self):
        expense = self.make_expense()
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse(
                'office:expense-void',
                args=[BusinessBranch.GARDEN, expense.pk],
            )
        )
        self.assertEqual(response.status_code, 302)
        expense.refresh_from_db()
        self.assertIsNotNone(expense.voided_at)
        self.assertEqual(expense.voided_by, self.staff)
        self.assertTrue(Expense.objects.filter(pk=expense.pk).exists())

        active = self.client.get(
            reverse('office:expense-list', args=[BusinessBranch.GARDEN])
        )
        all_entries = self.client.get(
            reverse('office:expense-list', args=[BusinessBranch.GARDEN]),
            {'status': 'all'},
        )
        self.assertNotContains(active, expense.supplier)
        self.assertContains(all_entries, expense.supplier)
        self.assertContains(all_entries, 'Void')

    def test_expense_export_includes_void_status_and_audit_fields(self):
        expense = self.make_expense()
        expense.void(self.staff)
        self.client.force_login(self.accountant)
        response = self.client.get(
            reverse('office:expense-export', args=[BusinessBranch.GARDEN])
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('Devon Garden Supplies', content)
        self.assertIn('42.50', content)
        self.assertIn('Void', content)
        self.assertIn('Voided by', content)

    def test_dashboard_total_excludes_void_expenses(self):
        self.make_expense(amount=Decimal('42.50'))
        void_expense = self.make_expense(
            supplier='Voided Supplier', amount=Decimal('10.00')
        )
        void_expense.void(self.staff)
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse('office:branch-dashboard', args=[BusinessBranch.GARDEN])
        )
        self.assertContains(response, '£42.50')


class AccountingReportTests(OfficeFixtureMixin, TestCase):
    def record_expense(self, amount=Decimal('20.00'), **overrides):
        values = {
            'branch': BusinessBranch.GARDEN,
            'expense_date': date(2026, 11, 5),
            'supplier': 'Trade Supplier',
            'category': Expense.Category.MATERIALS,
            'description': 'Materials',
            'amount': amount,
            'payment_method': Expense.PaymentMethod.CARD,
            'created_by': self.staff,
            'updated_by': self.staff,
        }
        values.update(overrides)
        return Expense.objects.create(**values)

    def report_url(self, **overrides):
        params = {
            'start': '2026-11-01',
            'end': '2026-11-30',
            'branch': 'all',
        }
        params.update(overrides)
        return reverse('office:accounting'), params

    def test_accountant_sees_sales_payments_expenses_and_cash_position(self):
        invoice = self.make_invoice().issue()
        invoice.mark_paid()
        self.record_expense()
        self.client.force_login(self.accountant)

        response = self.client.get(*self.report_url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['invoiced_sales'], Decimal('50.00'))
        self.assertEqual(response.context['recorded_payments'], Decimal('50.00'))
        self.assertEqual(response.context['expense_total'], Decimal('20.00'))
        self.assertEqual(response.context['cash_position'], Decimal('30.00'))
        self.assertContains(response, 'Accounting overview')

    def test_report_filters_branch_records(self):
        self.make_invoice().issue()
        self.record_expense()
        self.client.force_login(self.staff)

        garden = self.client.get(
            *self.report_url(branch=BusinessBranch.GARDEN)
        )
        rainwater = self.client.get(
            *self.report_url(branch=BusinessBranch.RAINWATER)
        )

        self.assertEqual(garden.context['invoiced_sales'], Decimal('50.00'))
        self.assertEqual(garden.context['expense_total'], Decimal('20.00'))
        self.assertEqual(rainwater.context['invoiced_sales'], Decimal('0.00'))
        self.assertEqual(rainwater.context['expense_total'], Decimal('0.00'))

    def test_current_outstanding_and_aged_invoice_are_reported(self):
        invoice = self.make_invoice().issue()
        self.client.force_login(self.staff)

        response = self.client.get(*self.report_url())

        self.assertEqual(response.context['current_outstanding'], Decimal('50.00'))
        self.assertEqual(len(response.context['aged_invoices']), 1)
        self.assertEqual(
            response.context['aged_invoices'][0]['invoice'], invoice
        )
        self.assertContains(response, invoice.number)

    def test_void_expenses_and_cancelled_invoices_are_excluded(self):
        invoice = self.make_invoice().issue()
        invoice.cancel()
        expense = self.record_expense()
        expense.void(self.staff)
        self.client.force_login(self.staff)

        response = self.client.get(*self.report_url())

        self.assertEqual(response.context['invoiced_sales'], Decimal('0.00'))
        self.assertEqual(response.context['expense_total'], Decimal('0.00'))
        self.assertEqual(response.context['current_outstanding'], Decimal('0.00'))

    def test_accounting_csv_exports_summary_and_aged_debt(self):
        invoice = self.make_invoice().issue()
        self.record_expense()
        self.client.force_login(self.accountant)
        response = self.client.get(
            *self.report_url(export='csv')
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        content = response.content.decode()
        self.assertIn('Avonmoor accounting summary', content)
        self.assertIn('Invoiced sales,50.00', content)
        self.assertIn('Recorded expenses,20.00', content)
        self.assertIn(invoice.number, content)

    def test_invalid_period_is_rejected_safely(self):
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse('office:accounting'),
            {'start': '2026-12-01', 'end': '2026-11-01'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, 'The report start date must be before the end date.'
        )

    def test_accounting_navigation_is_global(self):
        self.client.force_login(self.staff)
        accounting_url = reverse('office:accounting')
        office_home = self.client.get(reverse('office:dashboard'))
        garden = self.client.get(
            reverse('office:branch-dashboard', args=[BusinessBranch.GARDEN])
        )
        self.assertContains(office_home, f'href="{accounting_url}"')
        self.assertContains(garden, f'href="{accounting_url}"')


class InvoiceModelTests(OfficeFixtureMixin, TestCase):
    def test_issue_assigns_sequential_number_and_freezes_customer(self):
        invoice = self.make_invoice()
        issued = invoice.issue()
        self.assertEqual(issued.number, 'GPM-20261102-001')
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
        self.assertEqual(first.number, 'GPM-20261231-001')
        self.assertEqual(second.number, 'GPM-20270103-001')

    def test_branch_sequences_are_separate(self):
        garden_invoice = self.make_invoice().issue()
        rainwater_customer = Customer.objects.create(
            branch=BusinessBranch.RAINWATER,
            display_name='Rainwater Customer',
            billing_address_1='2 Water Lane',
            postcode='TQ10 9RW',
        )
        rainwater_invoice = Invoice.objects.create(
            branch=BusinessBranch.RAINWATER,
            customer=rainwater_customer,
            issue_date=date(2026, 11, 2),
            created_by=self.staff,
        )
        InvoiceLine.objects.create(
            invoice=rainwater_invoice,
            service_date=date(2026, 11, 2),
            description='Rainwater system installation',
            quantity=Decimal('1.00'),
            unit=WorkEntry.Unit.JOB,
            unit_price=Decimal('500.00'),
        )
        rainwater_invoice = rainwater_invoice.issue()
        self.assertEqual(garden_invoice.number, 'GPM-20261102-001')
        self.assertEqual(rainwater_invoice.number, 'RWH-20261102-001')

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

    def test_invoice_forms_expose_customer_ownership_for_safe_filtering(self):
        response = self.client.get(reverse('office:invoice-create'))
        self.assertContains(response, 'data-invoice-form')
        self.assertContains(
            response, f'data-customer-id="{self.customer.pk}"'
        )
        self.assertContains(
            response, f'data-property-id="{self.property.pk}"'
        )
        self.assertContains(response, 'office/js/invoice_form.js')

    def test_create_rejects_property_owned_by_another_customer(self):
        other = Customer.objects.create(
            display_name='Other Customer',
            billing_address_1='2 Other Road',
            postcode='TQ10 9BB',
        )
        other_property = Property.objects.create(
            customer=other,
            address_line_1='2 Other Road',
            postcode='TQ10 9BB',
        )
        response = self.client.post(
            reverse('office:invoice-create'),
            {
                'customer': self.customer.pk,
                'property': other_property.pk,
                'issue_date': '2026-11-02',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Invoice.objects.exists())
        self.assertIn('property', response.context['form'].errors)
        self.assertIn(
            'not one of the available choices',
            response.context['form'].errors['property'][0],
        )

    def test_rainwater_invoice_rejects_garden_customer(self):
        response = self.client.post(
            reverse('office:invoice-create', args=[BusinessBranch.RAINWATER]),
            {
                'customer': self.customer.pk,
                'property': self.property.pk,
                'issue_date': '2026-11-02',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Invoice.objects.exists())
        self.assertIn('customer', response.context['form'].errors)

    def test_edit_draft_can_add_completed_work_entry(self):
        invoice = self.make_invoice()
        existing_line = invoice.lines.get()
        extra_work = WorkEntry.objects.create(
            property=self.property,
            service_date=date(2026, 11, 2),
            category=WorkEntry.Category.LABOUR,
            description='Hedge trimming',
            quantity=Decimal('1.50'),
            unit=WorkEntry.Unit.HOURS,
            unit_price=Decimal('25.00'),
            created_by=self.staff,
        )
        response = self.client.post(
            reverse('office:invoice-edit', args=[invoice.pk]),
            {
                'customer': self.customer.pk,
                'property': self.property.pk,
                'issue_date': '2026-11-02',
                'work_entries': [extra_work.pk],
                'lines-TOTAL_FORMS': '2',
                'lines-INITIAL_FORMS': '1',
                'lines-MIN_NUM_FORMS': '0',
                'lines-MAX_NUM_FORMS': '1000',
                'lines-0-id': existing_line.pk,
                'lines-0-service_date': existing_line.service_date.isoformat(),
                'lines-0-category': existing_line.category,
                'lines-0-description': existing_line.description,
                'lines-0-quantity': existing_line.quantity,
                'lines-0-unit': existing_line.unit,
                'lines-0-unit_price': existing_line.unit_price,
                'lines-0-sort_order': existing_line.sort_order,
            },
        )
        self.assertRedirects(
            response, reverse('office:invoice-detail', args=[invoice.pk])
        )
        invoice.refresh_from_db()
        extra_work.refresh_from_db()
        self.assertEqual(invoice.lines.count(), 2)
        self.assertEqual(invoice.total, Decimal('87.50'))
        self.assertEqual(extra_work.invoice_line.invoice, invoice)

    def test_edit_draft_rejects_work_from_another_customer(self):
        invoice = self.make_invoice()
        existing_line = invoice.lines.get()
        other = Customer.objects.create(
            display_name='Other Customer',
            billing_address_1='2 Other Road',
            postcode='TQ10 9BB',
        )
        other_property = Property.objects.create(
            customer=other,
            address_line_1='2 Other Road',
            postcode='TQ10 9BB',
        )
        other_work = WorkEntry.objects.create(
            property=other_property,
            service_date=date(2026, 11, 2),
            description='Other garden',
            quantity=Decimal('1.00'),
            unit_price=Decimal('30.00'),
            created_by=self.staff,
        )
        response = self.client.post(
            reverse('office:invoice-edit', args=[invoice.pk]),
            {
                'customer': self.customer.pk,
                'property': self.property.pk,
                'issue_date': '2026-11-02',
                'work_entries': [other_work.pk],
                'lines-TOTAL_FORMS': '1',
                'lines-INITIAL_FORMS': '1',
                'lines-MIN_NUM_FORMS': '0',
                'lines-MAX_NUM_FORMS': '1000',
                'lines-0-id': existing_line.pk,
                'lines-0-service_date': existing_line.service_date.isoformat(),
                'lines-0-category': existing_line.category,
                'lines-0-description': existing_line.description,
                'lines-0-quantity': existing_line.quantity,
                'lines-0-unit': existing_line.unit,
                'lines-0-unit_price': existing_line.unit_price,
                'lines-0-sort_order': existing_line.sort_order,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(invoice.lines.count(), 1)
        self.assertFalse(other_work.is_invoiced)
        self.assertIn('work_entries', response.context['form'].errors)
        self.assertIn(
            'not one of the available choices',
            response.context['form'].errors['work_entries'][0],
        )

    def test_edit_draft_rejects_work_from_another_property_for_same_customer(self):
        invoice = self.make_invoice()
        second_property = Property.objects.create(
            customer=self.customer,
            address_line_1='2 Test Lane',
            postcode='TQ10 9AB',
        )
        second_work = WorkEntry.objects.create(
            property=second_property,
            service_date=date(2026, 11, 2),
            description='Second property work',
            quantity=Decimal('1.00'),
            unit_price=Decimal('25.00'),
            created_by=self.staff,
        )
        form = InvoiceForm(
            data={
                'customer': self.customer.pk,
                'property': self.property.pk,
                'issue_date': '2026-11-02',
                'work_entries': [second_work.pk],
            },
            instance=invoice,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('work_entries', form.errors)

    def test_edit_work_lock_query_avoids_postgres_outer_join(self):
        query = str(available_work_entries_for_update([self.work.pk]).query)
        self.assertNotIn('OUTER JOIN', query.upper())
        self.assertIn('NOT', query.upper())

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
        self.assertIn('GPM-20261102-001.pdf', response['Content-Disposition'])
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

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        EMAIL_HOST_USER='hello@avonmoor.co.uk',
    )
    @patch('office.views.append_message_to_sent')
    def test_issued_invoice_can_be_emailed_with_pdf_and_audit_record(
        self, append_to_sent
    ):
        invoice = self.make_invoice().issue()
        response = self.client.post(
            reverse('office:invoice-email', args=[invoice.pk]),
            {
                'recipient': 'alex@example.com',
                'subject': f'Invoice {invoice.number} from Avonmoor Ltd',
                'message': 'Please find the invoice attached.',
            },
        )
        self.assertRedirects(
            response, reverse('office:invoice-detail', args=[invoice.pk])
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['alex@example.com'])
        self.assertEqual(mail.outbox[0].attachments[0][0], f'{invoice.number}.pdf')
        self.assertEqual(mail.outbox[0].attachments[0][2], 'application/pdf')
        sent = InvoiceEmail.objects.get(invoice=invoice)
        self.assertEqual(sent.recipient, 'alex@example.com')
        self.assertEqual(sent.sent_by, self.staff)
        append_to_sent.assert_called_once()
        copied_email = append_to_sent.call_args.args[0]
        self.assertEqual(copied_email.subject, mail.outbox[0].subject)
        self.assertEqual(copied_email.attachments, mail.outbox[0].attachments)

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        EMAIL_HOST_USER='hello@avonmoor.co.uk',
    )
    @patch(
        'office.views.append_message_to_sent',
        side_effect=RuntimeError('IMAP unavailable'),
    )
    def test_sent_email_is_audited_when_sent_folder_copy_fails(
        self, append_to_sent
    ):
        invoice = self.make_invoice().issue()
        response = self.client.post(
            reverse('office:invoice-email', args=[invoice.pk]),
            {
                'recipient': 'alex@example.com',
                'subject': f'Invoice {invoice.number} from Avonmoor Ltd',
                'message': 'Please find the invoice attached.',
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(InvoiceEmail.objects.filter(invoice=invoice).exists())
        self.assertContains(response, 'could not be saved in Sent')
        append_to_sent.assert_called_once()

    def test_invoice_email_greeting_uses_contact_first_name(self):
        self.customer.contact_name = 'Paul Ream'
        self.customer.save()
        invoice = self.make_invoice().issue()
        response = self.client.get(
            reverse('office:invoice-email', args=[invoice.pk])
        )
        self.assertContains(response, 'Dear Paul,')
        self.assertNotContains(response, 'Dear Paul Ream,')
        self.assertContains(response, f'Please find attached invoice {invoice.number}.')
        self.assertNotContains(response, f'for £{invoice.total:.2f}')


class SentMailboxTests(TestCase):
    @override_settings(
        EMAIL_IMAP_HOST='imap.example.com',
        EMAIL_IMAP_PORT=993,
        EMAIL_HOST_USER='hello@avonmoor.co.uk',
        EMAIL_HOST_PASSWORD='mailbox-password',
        EMAIL_SENT_FOLDER='',
    )
    @patch('office.mailbox.imaplib.IMAP4_SSL')
    def test_complete_email_is_appended_to_advertised_sent_folder(
        self, imap_class
    ):
        connection = imap_class.return_value
        connection.list.return_value = (
            'OK',
            [
                b'(\\HasNoChildren) "/" "INBOX"',
                b'(\\HasNoChildren \\Sent) "/" "Sent Items"',
            ],
        )
        connection.append.return_value = ('OK', [b'APPEND completed'])
        email = mail.EmailMessage(
            subject='Invoice GPM-20261106-001 from Avonmoor Ltd',
            body='Please find the invoice attached.',
            from_email='hello@avonmoor.co.uk',
            to=['alex@example.com'],
        )
        email.attach('invoice.pdf', b'%PDF-test', 'application/pdf')

        folder = append_message_to_sent(email)

        self.assertEqual(folder, 'Sent Items')
        imap_class.assert_called_once_with('imap.example.com', 993)
        connection.login.assert_called_once_with(
            'hello@avonmoor.co.uk', 'mailbox-password'
        )
        append_args = connection.append.call_args.args
        self.assertEqual(append_args[0], '"Sent Items"')
        self.assertEqual(append_args[1], '(\\Seen)')
        self.assertIn(
            b'Subject: Invoice GPM-20261106-001 from Avonmoor Ltd',
            append_args[3],
        )
        self.assertIn(b'filename="invoice.pdf"', append_args[3])
        connection.logout.assert_called_once()

    @override_settings(
        EMAIL_IMAP_HOST='imap.example.com',
        EMAIL_IMAP_PORT=993,
        EMAIL_HOST_USER='hello@avonmoor.co.uk',
        EMAIL_HOST_PASSWORD='mailbox-password',
        EMAIL_SENT_FOLDER='Sent',
    )
    @patch('office.mailbox.imaplib.IMAP4_SSL')
    def test_configured_sent_folder_does_not_depend_on_list(self, imap_class):
        connection = imap_class.return_value
        connection.append.return_value = ('OK', [b'APPEND completed'])
        email = mail.EmailMessage(
            subject='Invoice',
            body='Attached.',
            from_email='hello@avonmoor.co.uk',
            to=['alex@example.com'],
        )

        folder = append_message_to_sent(email)

        self.assertEqual(folder, 'Sent')
        connection.list.assert_not_called()
        self.assertEqual(connection.append.call_args.args[0], '"Sent"')
