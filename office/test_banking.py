import json
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .banking import (
    MonzoAPIError,
    auto_match_transaction,
    expense_suggestion,
    import_bank_csv,
    is_fuel_transaction,
    match_payment,
    retry_auto_matching,
    sync_monzo_transactions,
)
from .models import (
    BankConnection,
    BankTransaction,
    Customer,
    Expense,
    ExpenseImportRule,
    Invoice,
    InvoiceLine,
    PaymentMatch,
)


class BankingFixtureMixin:
    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            username='pete',
            password='test-password',
            is_staff=True,
            is_superuser=True,
        )
        self.accountant = get_user_model().objects.create_user(
            username='accountant',
            password='test-password',
            is_staff=True,
        )
        self.customer = Customer.objects.create(
            display_name='Paul Ream',
            billing_address_1='1 Test Lane',
            postcode='TQ10 9AA',
        )

    def issued_invoice(self, amount='87.50'):
        invoice = Invoice.objects.create(
            customer=self.customer,
            issue_date=date(2026, 11, 6),
            created_by=self.owner,
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            service_date=date(2026, 11, 5),
            description='Garden maintenance',
            quantity=Decimal('1.00'),
            unit_price=Decimal(amount),
        )
        return invoice.issue()

    def bank_transaction(self, *, amount_minor=8750, reference='', description='Paul Ream'):
        return BankTransaction.objects.create(
            source=BankTransaction.Source.MONZO,
            external_id=f'monzo:tx-{BankTransaction.objects.count() + 1}',
            account_id='acc-avonmoor',
            amount_minor=amount_minor,
            currency='GBP',
            transaction_at=timezone.now(),
            settled_at=timezone.now(),
            description=description,
            reference=reference,
        )


class PaymentMatchingTests(BankingFixtureMixin, TestCase):
    def test_exact_reference_and_balance_match_automatically(self):
        invoice = self.issued_invoice()
        bank_transaction = self.bank_transaction(reference=invoice.number)

        payment_match = auto_match_transaction(bank_transaction)

        self.assertIsNotNone(payment_match)
        self.assertEqual(payment_match.method, PaymentMatch.Method.AUTOMATIC)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.PAID)
        self.assertIsNotNone(invoice.paid_at)

    def test_matching_amount_without_invoice_or_customer_name_stays_in_review(self):
        invoice = self.issued_invoice()
        bank_transaction = self.bank_transaction(
            reference='Garden work', description='Unknown payer'
        )

        self.assertIsNone(auto_match_transaction(bank_transaction))
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.ISSUED)
        self.assertFalse(PaymentMatch.objects.exists())

    def test_exact_balance_and_full_customer_name_match_automatically(self):
        invoice = self.issued_invoice()
        bank_transaction = self.bank_transaction(
            reference='Garden work', description='Paul Ream'
        )

        payment_match = auto_match_transaction(bank_transaction)

        self.assertIsNotNone(payment_match)
        self.assertEqual(payment_match.invoice, invoice)

    def test_exact_balance_and_unique_surname_match_automatically(self):
        invoice = self.issued_invoice()
        bank_transaction = self.bank_transaction(
            reference='REAM', description='Incoming transfer'
        )

        payment_match = auto_match_transaction(bank_transaction)

        self.assertIsNotNone(payment_match)
        self.assertEqual(payment_match.invoice, invoice)

    def test_same_customer_with_two_equal_invoices_stays_in_review(self):
        self.issued_invoice()
        self.issued_invoice()
        bank_transaction = self.bank_transaction(
            reference='Paul Ream', description='Incoming transfer'
        )

        self.assertIsNone(auto_match_transaction(bank_transaction))
        self.assertFalse(PaymentMatch.objects.exists())

    def test_shared_surname_stays_in_review(self):
        invoice = self.issued_invoice()
        Customer.objects.create(
            display_name='Sarah Ream',
            billing_address_1='2 Test Lane',
            postcode='TQ10 9AA',
        )
        bank_transaction = self.bank_transaction(
            reference='Ream', description='Incoming transfer'
        )

        self.assertIsNone(auto_match_transaction(bank_transaction))
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.ISSUED)
        self.assertFalse(PaymentMatch.objects.exists())

    def test_previously_paid_invoice_can_be_reconciled_by_reference(self):
        invoice = self.issued_invoice()
        invoice.mark_paid()
        original_paid_at = invoice.paid_at
        bank_transaction = self.bank_transaction(
            reference=invoice.number, description='Incoming transfer'
        )

        payment_match = auto_match_transaction(bank_transaction)

        self.assertIsNotNone(payment_match)
        self.assertEqual(payment_match.invoice, invoice)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.PAID)
        self.assertEqual(invoice.paid_at, original_paid_at)

    def test_retry_matching_reconciles_existing_review_payment(self):
        bank_transaction = self.bank_transaction(
            amount_minor=10000,
            reference='Meikle',
            description='Meikle',
        )
        meikle = Customer.objects.create(
            display_name='Alex Meikle',
            billing_address_1='2 Test Lane',
            postcode='TQ10 9AA',
        )
        invoice = Invoice.objects.create(
            customer=meikle,
            issue_date=date(2026, 11, 4),
            created_by=self.owner,
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            service_date=date(2026, 11, 4),
            description='Garden maintenance',
            quantity=Decimal('4.00'),
            unit_price=Decimal('25.00'),
        )
        invoice.issue()

        self.assertEqual(retry_auto_matching(), 1)
        payment_match = PaymentMatch.objects.get(transaction=bank_transaction)
        self.assertEqual(payment_match.invoice, invoice)

    def test_paid_invoice_with_bank_match_cannot_receive_duplicate_match(self):
        invoice = self.issued_invoice()
        first = self.bank_transaction(reference=invoice.number)
        self.assertIsNotNone(auto_match_transaction(first))
        duplicate = self.bank_transaction(reference=invoice.number)

        self.assertIsNone(auto_match_transaction(duplicate))
        self.assertEqual(PaymentMatch.objects.filter(invoice=invoice).count(), 1)

    def test_reference_with_wrong_amount_stays_in_review(self):
        invoice = self.issued_invoice()
        bank_transaction = self.bank_transaction(
            amount_minor=8000, reference=invoice.number
        )

        self.assertIsNone(auto_match_transaction(bank_transaction))
        self.assertFalse(PaymentMatch.objects.exists())

    def test_manual_match_requires_exact_outstanding_balance(self):
        invoice = self.issued_invoice()
        bank_transaction = self.bank_transaction(amount_minor=8000)

        with self.assertRaisesMessage(
            ValidationError, 'exactly equal the invoice outstanding balance'
        ):
            match_payment(
                bank_transaction,
                invoice,
                method=PaymentMatch.Method.MANUAL,
                user=self.accountant,
            )

    def test_accountant_can_manually_match_and_undo(self):
        invoice = self.issued_invoice()
        bank_transaction = self.bank_transaction(reference='Missing reference')
        self.client.force_login(self.accountant)

        response = self.client.post(
            reverse('office:payment-match', args=[bank_transaction.pk]),
            {'invoice': invoice.pk},
        )

        self.assertRedirects(response, reverse('office:payments'))
        payment_match = PaymentMatch.objects.get(transaction=bank_transaction)
        self.assertEqual(payment_match.matched_by, self.accountant)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.PAID)

        response = self.client.post(
            reverse('office:payment-unmatch', args=[payment_match.pk])
        )
        self.assertRedirects(response, reverse('office:payments'))
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.ISSUED)
        self.assertIsNone(invoice.paid_at)

    def test_non_avonmoor_payment_can_be_ignored_and_restored(self):
        bank_transaction = self.bank_transaction(description='Hot Pressed')
        self.client.force_login(self.accountant)

        self.client.post(
            reverse('office:payment-ignore', args=[bank_transaction.pk])
        )
        bank_transaction.refresh_from_db()
        self.assertEqual(bank_transaction.ignored_by, self.accountant)
        self.assertIsNotNone(bank_transaction.ignored_at)

        self.client.post(
            reverse('office:payment-restore', args=[bank_transaction.pk])
        )
        bank_transaction.refresh_from_db()
        self.assertIsNone(bank_transaction.ignored_at)
        self.assertIsNone(bank_transaction.ignored_by)


class BankCSVTests(BankingFixtureMixin, TestCase):
    def test_csv_import_is_duplicate_safe_and_auto_matches(self):
        invoice = self.issued_invoice()
        content = (
            'Transaction ID,Date,Time,Amount,Currency,Name,Reference\n'
            f'tx_csv_1,06/11/2026,10:30,87.50,GBP,Paul Ream,{invoice.number}\n'
            'tx_csv_debit,06/11/2026,10:31,-10.00,GBP,Shop,Expense\n'
        ).encode('utf-8')

        first = import_bank_csv(SimpleUploadedFile('monzo.csv', content))
        second = import_bank_csv(SimpleUploadedFile('monzo.csv', content))

        self.assertEqual(first, (2, 0, 1))
        self.assertEqual(second, (0, 2, 0))
        self.assertEqual(BankTransaction.objects.count(), 2)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.PAID)

    def test_csv_upload_page_is_available_to_accountant(self):
        self.client.force_login(self.accountant)
        response = self.client.get(reverse('office:payments'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'CSV fallback')


class ExpenseInboxTests(BankingFixtureMixin, TestCase):
    def expense_post_data(self, **overrides):
        data = {
            'branch': 'garden',
            'supplier': 'IONOS',
            'category': Expense.Category.OFFICE,
            'description': 'Website and domain hosting',
            'property': '',
            'reference': 'Monthly hosting',
            'notes': '',
        }
        data.update(overrides)
        return data

    def test_accountant_records_actual_outgoing_payment_as_expense(self):
        outgoing = self.bank_transaction(
            amount_minor=-1299,
            description='IONOS SE',
            reference='Monthly hosting',
        )
        self.client.force_login(self.accountant)

        response = self.client.post(
            reverse('office:expense-bank-review', args=[outgoing.pk]),
            self.expense_post_data(),
        )

        self.assertRedirects(response, reverse('office:expense-inbox'))
        expense = Expense.objects.get()
        self.assertEqual(expense.bank_transaction, outgoing)
        self.assertEqual(expense.amount, Decimal('12.99'))
        self.assertEqual(expense.created_by, self.accountant)
        self.assertEqual(expense.branch, 'garden')

    def test_one_bank_transaction_cannot_create_two_expenses(self):
        outgoing = self.bank_transaction(
            amount_minor=-1299, description='IONOS SE'
        )
        self.client.force_login(self.accountant)
        url = reverse('office:expense-bank-review', args=[outgoing.pk])

        self.client.post(url, self.expense_post_data())
        second = self.client.post(url, self.expense_post_data())

        self.assertRedirects(second, reverse('office:expense-inbox'))
        self.assertEqual(Expense.objects.count(), 1)

    def test_fuel_is_excluded_and_cannot_be_recorded(self):
        fuel = self.bank_transaction(
            amount_minor=-6500,
            description='SHELL SOUTH BRENT',
            reference='Diesel',
        )
        self.assertTrue(is_fuel_transaction(fuel))
        self.client.force_login(self.owner)

        review = self.client.get(reverse('office:expense-inbox'))
        excluded = self.client.get(
            reverse('office:expense-inbox'), {'status': 'excluded'}
        )
        record = self.client.get(
            reverse('office:expense-bank-review', args=[fuel.pk])
        )

        self.assertNotContains(review, 'SHELL SOUTH BRENT')
        self.assertContains(excluded, 'Fuel excluded')
        self.assertRedirects(record, reverse('office:expense-inbox'))
        self.assertFalse(Expense.objects.exists())

    def test_remembered_supplier_prefills_future_payment(self):
        first = self.bank_transaction(
            amount_minor=-1299, description='IONOS SE'
        )
        self.client.force_login(self.owner)
        self.client.post(
            reverse('office:expense-bank-review', args=[first.pk]),
            self.expense_post_data(remember_supplier='on'),
        )
        self.assertEqual(ExpenseImportRule.objects.count(), 1)
        second = self.bank_transaction(
            amount_minor=-1499, description='IONOS SE'
        )

        suggestion = expense_suggestion(second)

        self.assertEqual(suggestion['supplier'], 'IONOS')
        self.assertEqual(suggestion['branch'], 'garden')
        self.assertEqual(suggestion['category'], Expense.Category.OFFICE)
        self.assertEqual(suggestion['description'], 'Website and domain hosting')

    def test_outgoing_can_be_excluded_and_restored(self):
        outgoing = self.bank_transaction(
            amount_minor=-5000, description='Personal transfer'
        )
        self.client.force_login(self.accountant)

        self.client.post(
            reverse('office:expense-bank-ignore', args=[outgoing.pk])
        )
        outgoing.refresh_from_db()
        self.assertEqual(outgoing.ignored_by, self.accountant)
        self.assertIsNotNone(outgoing.ignored_at)

        self.client.post(
            reverse('office:expense-bank-restore', args=[outgoing.pk])
        )
        outgoing.refresh_from_db()
        self.assertIsNone(outgoing.ignored_at)
        self.assertIsNone(outgoing.ignored_by)

    def test_incoming_payment_does_not_appear_in_expense_inbox(self):
        self.bank_transaction(description='Paul Ream')
        self.client.force_login(self.accountant)

        response = self.client.get(
            reverse('office:expense-inbox'), {'status': 'all'}
        )

        self.assertNotContains(response, 'Paul Ream')

    def test_pending_card_payment_waits_until_settled(self):
        pending = self.bank_transaction(
            amount_minor=-1299, description='IONOS PENDING'
        )
        pending.settled_at = None
        pending.save(update_fields=['settled_at'])
        self.client.force_login(self.accountant)

        response = self.client.get(
            reverse('office:expense-inbox'), {'status': 'all'}
        )

        self.assertNotContains(response, 'IONOS PENDING')

    @patch('office.banking.connection_token', return_value='access-token')
    @patch('office.banking._monzo_request')
    def test_monzo_sync_imports_incoming_and_outgoing(self, request, token):
        now = timezone.now().isoformat()
        request.return_value = {
            'transactions': [
                {
                    'id': 'tx_credit',
                    'account_id': 'acc-avonmoor',
                    'amount': 5000,
                    'currency': 'GBP',
                    'created': now,
                    'settled': now,
                    'description': 'Customer',
                },
                {
                    'id': 'tx_debit',
                    'account_id': 'acc-avonmoor',
                    'amount': -1299,
                    'currency': 'GBP',
                    'created': now,
                    'settled': now,
                    'description': 'IONOS SE',
                },
            ]
        }
        connection = BankConnection.objects.create(
            connected_by=self.owner,
            account_id='acc-avonmoor',
            active=True,
        )

        imported, matched = sync_monzo_transactions(connection)

        self.assertEqual(imported, 2)
        self.assertEqual(matched, 0)
        self.assertEqual(BankTransaction.objects.filter(amount_minor__lt=0).count(), 1)
        token.assert_called_once_with(connection)


class MonzoConnectionTests(BankingFixtureMixin, TestCase):
    @override_settings(SECRET_KEY='encryption-test-key')
    def test_bank_tokens_are_encrypted_at_rest(self):
        connection = BankConnection.objects.create(
            connected_by=self.owner,
            account_id='acc-avonmoor',
        )
        connection.set_tokens('access-secret', 'refresh-secret')
        connection.save()

        self.assertNotIn('access-secret', connection.access_token_encrypted)
        self.assertNotIn('refresh-secret', connection.refresh_token_encrypted)
        self.assertEqual(connection.access_token(), 'access-secret')
        self.assertEqual(connection.refresh_token(), 'refresh-secret')

    @override_settings(
        MONZO_CLIENT_ID='client-id',
        MONZO_CLIENT_SECRET='client-secret',
        MONZO_REDIRECT_URI='https://www.avonmoor.co.uk/office/payments/monzo/callback/',
    )
    def test_only_owner_can_start_monzo_connection(self):
        self.client.force_login(self.accountant)
        response = self.client.post(reverse('office:monzo-connect'))
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.owner)
        response = self.client.post(reverse('office:monzo-connect'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith('https://auth.monzo.com/'))
        self.assertIn('monzo_oauth_state', self.client.session)

    @override_settings(
        MONZO_CLIENT_ID='client-id',
        MONZO_CLIENT_SECRET='client-secret',
        MONZO_REDIRECT_URI='https://www.avonmoor.co.uk/office/payments/monzo/callback/',
    )
    @patch('office.banking_views.exchange_authorization_code')
    def test_callback_rejects_incorrect_oauth_state(self, exchange):
        self.client.force_login(self.owner)
        session = self.client.session
        session['monzo_oauth_state'] = 'expected-state'
        session.save()

        response = self.client.get(
            reverse('office:monzo-callback'),
            {'state': 'wrong-state', 'code': 'temporary-code'},
        )

        self.assertRedirects(response, reverse('office:payments'))
        exchange.assert_not_called()
        self.assertFalse(BankConnection.objects.exists())

    @override_settings(
        SECRET_KEY='oauth-encryption-test-key',
        MONZO_CLIENT_ID='client-id',
        MONZO_CLIENT_SECRET='client-secret',
        MONZO_REDIRECT_URI='https://www.avonmoor.co.uk/office/payments/monzo/callback/',
    )
    @patch('office.banking_views.exchange_authorization_code')
    def test_valid_callback_stores_encrypted_tokens_then_waits_for_app_approval(
        self, exchange
    ):
        exchange.return_value = {
            'access_token': 'access-secret',
            'refresh_token': 'refresh-secret',
            'expires_in': 21600,
        }
        self.client.force_login(self.owner)
        session = self.client.session
        session['monzo_oauth_state'] = 'expected-state'
        session.save()

        response = self.client.get(
            reverse('office:monzo-callback'),
            {'state': 'expected-state', 'code': 'temporary-code'},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('office:payments'))
        connection = BankConnection.objects.get(provider='monzo')
        self.assertFalse(connection.active)
        self.assertNotIn('access-secret', connection.access_token_encrypted)
        self.assertEqual(connection.access_token(), 'access-secret')
        self.assertEqual(connection.refresh_token(), 'refresh-secret')

        response = self.client.get(reverse('office:payments'))
        self.assertContains(response, 'Monzo is awaiting approval.')
        self.assertContains(response, 'Continue setup')
        self.assertNotContains(response, 'Connect Monzo')

    @override_settings(SECRET_KEY='oauth-encryption-test-key')
    @patch('office.banking_views.list_monzo_accounts')
    def test_account_selection_explains_pending_monzo_app_approval(
        self, list_accounts
    ):
        connection = BankConnection.objects.create(
            provider='monzo', connected_by=self.owner
        )
        connection.set_tokens('access-secret', 'refresh-secret')
        connection.save()
        list_accounts.side_effect = MonzoAPIError(
            'Access forbidden due to insufficient permissions',
            status_code=403,
        )
        self.client.force_login(self.owner)

        response = self.client.get(reverse('office:monzo-account'), follow=True)

        self.assertRedirects(response, reverse('office:payments'))
        self.assertContains(response, 'Monzo approval is still required.')
        self.assertNotContains(
            response, 'Access forbidden due to insufficient permissions'
        )

    @patch('office.banking_views.fetch_monzo_transaction')
    def test_webhook_fetches_transaction_from_monzo_before_matching(self, fetch):
        invoice = self.issued_invoice()
        BankConnection.objects.create(
            connected_by=self.owner,
            account_id='acc-avonmoor',
            account_name='Avonmoor Ltd',
            active=True,
        )
        fetch.return_value = {
            'id': 'tx_verified',
            'account_id': 'acc-avonmoor',
            'amount': 8750,
            'currency': 'GBP',
            'created': timezone.now().isoformat(),
            'settled': timezone.now().isoformat(),
            'description': 'Paul Ream',
            'notes': invoice.number,
            'metadata': {},
        }

        response = self.client.post(
            reverse('office:monzo-webhook'),
            data=json.dumps(
                {
                    'type': 'transaction.created',
                    'data': {
                        'id': 'tx_untrusted',
                        'account_id': 'acc-avonmoor',
                        'amount': 1,
                    },
                }
            ),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 202)
        fetch.assert_called_once()
        self.assertTrue(
            PaymentMatch.objects.filter(invoice=invoice).exists()
        )

    @patch('office.banking_views.fetch_monzo_transaction')
    def test_webhook_stores_outgoing_transaction_for_expense_review(self, fetch):
        BankConnection.objects.create(
            connected_by=self.owner,
            account_id='acc-avonmoor',
            account_name='Avonmoor Ltd',
            active=True,
        )
        fetch.return_value = {
            'id': 'tx_ionos',
            'account_id': 'acc-avonmoor',
            'amount': -1299,
            'currency': 'GBP',
            'created': timezone.now().isoformat(),
            'settled': timezone.now().isoformat(),
            'description': 'IONOS SE',
            'notes': 'Monthly hosting',
            'metadata': {},
        }

        response = self.client.post(
            reverse('office:monzo-webhook'),
            data=json.dumps(
                {
                    'type': 'transaction.created',
                    'data': {
                        'id': 'tx_untrusted',
                        'account_id': 'acc-avonmoor',
                    },
                }
            ),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 202)
        bank_transaction = BankTransaction.objects.get(
            external_id='monzo:tx_ionos'
        )
        self.assertEqual(bank_transaction.amount_minor, -1299)
        self.assertFalse(PaymentMatch.objects.exists())

    @patch('office.banking_views.fetch_monzo_transaction')
    def test_webhook_for_unconnected_account_is_ignored(self, fetch):
        response = self.client.post(
            reverse('office:monzo-webhook'),
            data=json.dumps(
                {
                    'type': 'transaction.created',
                    'data': {'id': 'tx_spoofed', 'account_id': 'other-account'},
                }
            ),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 202)
        fetch.assert_not_called()
        self.assertFalse(BankTransaction.objects.exists())
