from datetime import date
from decimal import Decimal
import csv
import io
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from .models import MileageJourney, MileageClaim, MileageClaimLine, MileageLedger, Expense, Customer, Property, WorkEntry
from .mileage import allocation, tax_year, review_journey, generate_claim, transition_claim
from .mileage_forms import MileageJourneyForm
from .views import build_accounting_report


class MileageTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user('owner', is_staff=True, is_superuser=True)
        self.accountant = get_user_model().objects.create_user('accountant', is_staff=True)
        self.visitor = get_user_model().objects.create_user('visitor')
        self.ledger = MileageLedger.objects.get(pk=1)

    def journey(self, day=date(2026, 10, 10), miles='20', branch='garden', approve=True, **extra):
        j = MileageJourney.objects.create(ledger=self.ledger, journey_date=day, miles=Decimal(miles), branch=branch, start='South Brent', destination='Client property', purpose='Garden maintenance', created_by=self.owner, **extra)
        if approve:
            j = review_journey(j.pk, self.accountant)
        return j

    def claim(self, branch='garden', month=date(2026, 10, 1)):
        return generate_claim(month, branch, self.accountant)

    def test_tax_year_boundaries_and_historical_rate(self):
        for day, year, rate in [(date(2025, 10, 1), 2025, '0.45'), (date(2026, 1, 1), 2025, '0.45'), (date(2026, 4, 5), 2025, '0.45'), (date(2026, 4, 6), 2026, '0.55')]:
            self.assertEqual(tax_year(day), year)
            self.assertEqual(allocation(day, Decimal(10), Decimal(0))['amount'], Decimal(rate) * 10)

    def test_threshold_split_and_exhausted(self):
        for before, high, low, amount in [('9990', '10', '10', '8.00'), ('10000', '0', '20', '5.00'), ('10001', '0', '20', '5.00')]:
            result = allocation(date(2026, 10, 1), Decimal(20), Decimal(before))
            self.assertEqual(result['higher_rate_miles'], Decimal(high))
            self.assertEqual(result['lower_rate_miles'], Decimal(low))
            self.assertEqual(result['amount'], Decimal(amount))
        self.assertEqual(allocation(date(2026, 4, 5), Decimal(20), Decimal(9990))['amount'], Decimal('7.00'))

    def test_branches_share_threshold_but_claims_are_separate(self):
        self.journey(day=date(2026, 10, 1), miles='9990')
        self.journey(day=date(2026, 10, 2), branch='rainwater')
        garden = self.claim()
        rain = self.claim('rainwater')
        self.assertEqual(garden.lines.count(), 1)
        self.assertEqual(rain.lines.get().cumulative_before, Decimal(9990))
        self.assertEqual(rain.total, Decimal('8.00'))

    def test_allowance_resets_on_april_six_not_january(self):
        self.journey(day=date(2025, 10, 1), miles='10000')
        self.journey(day=date(2026, 1, 1), miles='10')
        self.journey(day=date(2026, 4, 5), miles='10')
        self.journey(day=date(2026, 4, 6), miles='10')
        self.assertEqual(self.claim(month=date(2026, 1, 1)).total, Decimal('2.50'))
        april = self.claim(month=date(2026, 4, 1))
        self.assertEqual(april.total, Decimal('8.00'))
        self.assertEqual([line.tax_year for line in april.lines.all()], [2025, 2026])

    def test_odometer_distance_and_return_not_doubled(self):
        j = self.journey(approve=False, odometer_start=Decimal('1000'), odometer_finish=Decimal('1023.40'), return_journey=True)
        j.full_clean()
        self.assertEqual(j.total_miles, Decimal('23.40'))
        manual = self.journey(return_journey=True)
        self.assertEqual(manual.total_miles, Decimal(40))

    def test_invalid_distance_and_future_date(self):
        for kwargs in [{'miles': '0'}, {'odometer_start': Decimal(10)}, {'odometer_start': Decimal(10), 'odometer_finish': Decimal(9)}, {'journey_date': date(2099, 1, 1)}]:
            j = self.journey(approve=False)
            for key, value in kwargs.items():
                setattr(j, key, value)
            with self.assertRaises(ValidationError):
                j.full_clean()

    def test_form_odometer_only_calculates(self):
        form = MileageJourneyForm({'journey_date': '2026-10-01', 'start': 'Home', 'destination': 'Site', 'purpose': 'Maintenance', 'odometer_start': '1200', 'odometer_finish': '1225', 'return_journey': 'on'}, branch='garden', instance=MileageJourney(ledger=self.ledger, created_by=self.owner))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.instance.total_miles, Decimal(25))

    def test_cross_branch_and_inconsistent_links_rejected(self):
        customer = Customer.objects.create(branch='rainwater', display_name='Rain client', billing_address_1='Site', postcode='TQ10 9AA')
        prop = Property.objects.create(customer=customer, address_line_1='Site', postcode='TQ10 9AA')
        j = self.journey(approve=False, customer=customer, property=prop)
        with self.assertRaises(ValidationError):
            j.full_clean()
        form = MileageJourneyForm({'journey_date':'2026-10-01','start':'A','destination':'B','purpose':'Work','miles':'10','customer':customer.pk}, branch='garden', instance=MileageJourney(ledger=self.ledger, created_by=self.owner))
        self.assertFalse(form.is_valid())

    def test_only_approved_journeys_and_correct_month_in_draft(self):
        self.journey(approve=False)
        self.journey(day=date(2026, 9, 1))
        with self.assertRaises(ValidationError):
            self.claim()
        self.assertEqual(MileageClaim.objects.count(), 0)
        j = self.journey()
        claim = self.claim()
        self.assertEqual(list(claim.lines.values_list('journey_id', flat=True)), [j.pk])
        self.assertFalse(Expense.objects.exists())

    def test_duplicate_generation_and_approval_are_safe(self):
        j = self.journey()
        claim = self.claim()
        self.assertEqual(self.claim().pk, claim.pk)
        self.assertEqual(MileageClaimLine.objects.filter(active=True).count(), 1)
        transition_claim(claim.pk, 'approve', self.owner)
        with self.assertRaises(ValidationError):
            transition_claim(claim.pk, 'approve', self.owner)
        with self.assertRaises(ValidationError):
            self.claim()
        self.assertEqual(Expense.objects.count(), 1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            MileageClaimLine.objects.create(claim=claim, journey=j, tax_year=2026, cumulative_before=0, miles=20, higher_rate_miles=20, higher_rate='.55', lower_rate_miles=0, amount=11)

    def test_accountant_can_review_but_owner_must_approve_expense(self):
        self.journey()
        claim = self.claim()
        for action in ['approve', 'paid', 'void']:
            with self.assertRaises(PermissionDenied):
                transition_claim(claim.pk, action, self.accountant)
        self.assertFalse(Expense.objects.exists())
        transition_claim(claim.pk, 'approve', self.owner)
        expense = Expense.objects.get()
        self.assertEqual(expense.category, 'mileage')
        self.assertEqual(expense.supplier, 'Pete Cookson')
        self.assertFalse(Expense.objects.filter(category='fuel').exists())

    def test_backdated_approval_blocked_after_final_claim(self):
        self.journey()
        claim = self.claim()
        transition_claim(claim.pk, 'approve', self.owner)
        earlier = self.journey(day=date(2026, 9, 1), approve=False)
        with self.assertRaises(ValidationError):
            review_journey(earlier.pk, self.accountant)
        transition_claim(claim.pk, 'void', self.owner, 'Correct historical record')
        review_journey(earlier.pk, self.accountant)

    def test_draft_recalculates_when_earlier_journey_approved(self):
        self.journey()
        claim = self.claim()
        self.journey(day=date(2026, 9, 1), miles='10000')
        transition_claim(claim.pk, 'approve', self.owner)
        claim.refresh_from_db()
        self.assertEqual(claim.total, Decimal('5.00'))

    def test_void_preserves_audit_and_releases_journeys(self):
        self.journey()
        claim = self.claim()
        transition_claim(claim.pk, 'approve', self.owner)
        transition_claim(claim.pk, 'void', self.owner, 'Incorrect grouping')
        claim.refresh_from_db()
        self.assertTrue(claim.expense.is_void)
        self.assertFalse(claim.lines.get().active)
        replacement = self.claim()
        self.assertNotEqual(replacement.pk, claim.pk)
        self.assertEqual(MileageClaimLine.objects.count(), 2)

    def test_paid_requires_reference_and_cannot_be_voided(self):
        self.journey()
        claim = self.claim()
        with self.assertRaises(ValidationError):
            transition_claim(claim.pk, 'paid', self.owner, 'bank')
        transition_claim(claim.pk, 'approve', self.owner)
        with self.assertRaises(ValidationError):
            transition_claim(claim.pk, 'paid', self.owner)
        transition_claim(claim.pk, 'paid', self.owner, 'MONZO-PETE-001')
        with self.assertRaises(ValidationError):
            transition_claim(claim.pk, 'void', self.owner, 'reason')

    def test_accounting_unpaid_expense_is_not_cash_spent(self):
        self.journey()
        claim = self.claim()
        transition_claim(claim.pk, 'approve', self.owner)
        report = build_accounting_report(date(2026, 10, 1), date(2026, 10, 31))
        self.assertEqual(report['expense_total'], Decimal(11))
        self.assertEqual(report['cash_position'], 0)
        self.assertEqual(report['mileage_owed'], Decimal(11))
        transition_claim(claim.pk, 'paid', self.owner, 'bank-reference')
        report = build_accounting_report(date(2026, 1, 1), date(2026, 12, 31))
        self.assertEqual(report['cash_position'], Decimal(-11))
        self.assertEqual(report['mileage_owed'], 0)
        self.assertEqual(sum(row['position'] for row in report['months']), Decimal(-11))
        self.assertEqual(build_accounting_report(date(2026, 1, 1), date(2026, 12, 31), 'rainwater')['expense_total'], 0)

    def test_routes_permissions_and_branch_isolation(self):
        j = self.journey(approve=False)
        url = reverse('office:mileage-list', args=['garden'])
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.visitor)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.accountant)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(reverse('office:mileage-review', args=['garden',j.pk,'approve'])).status_code, 302)
        self.assertEqual(self.client.get(reverse('office:mileage-edit', args=['rainwater',j.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('office:mileage-edit', args=['garden',j.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('office:mileage-review', args=['garden',j.pk,'void'])).status_code, 403)
        claim = self.claim()
        self.assertEqual(self.client.post(reverse('office:mileage-claim', args=['garden',claim.pk]), {'action':'approve'}).status_code, 403)
        self.assertEqual(self.client.get(reverse('office:mileage-claim', args=['rainwater',claim.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('office:mileage-claim', args=['garden',claim.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('office:mileage-create', args=['garden'])).status_code, 200)

    def test_generated_expense_cannot_be_edited_or_voided_outside_claim(self):
        self.journey()
        claim = transition_claim(self.claim().pk, 'approve', self.owner)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse('office:expense-edit', args=['garden',claim.expense_id])).status_code, 404)
        self.assertEqual(self.client.post(reverse('office:expense-void', args=['garden',claim.expense_id])).status_code, 404)

    def test_csv_evidence_includes_rates_audit_payment_and_formula_safety(self):
        j = self.journey()
        MileageJourney.objects.filter(pk=j.pk).update(purpose='=FORMULA()')
        claim = transition_claim(self.claim().pk, 'approve', self.owner)
        transition_claim(claim.pk, 'paid', self.owner, 'BANK-123')
        self.client.force_login(self.accountant)
        response = self.client.get(reverse('office:mileage-export', args=['garden']))
        rows = list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
        self.assertEqual(len(rows[0]), len(rows[1]))
        self.assertIn("'=FORMULA()", rows[1])
        self.assertIn('BANK-123', rows[1])
        self.assertIn('0.55', rows[1])
        self.assertIn('Pete Cookson', rows[1])

    def test_manual_expense_form_cannot_forge_mileage_or_fuel(self):
        from .forms import ExpenseForm
        for category in ['mileage', 'fuel']:
            form = ExpenseForm({'expense_date':'2026-10-01','supplier':'Pete','category':category,'description':'Test','amount':'10','payment_method':'bank'})
            self.assertFalse(form.is_valid())
            self.assertIn('category', form.errors)

    def test_phone_entry_to_monthly_claim_http_workflow(self):
        self.client.force_login(self.accountant)
        response = self.client.post(reverse('office:mileage-create', args=['garden']), {
            'journey_date': '2025-10-15', 'start': 'South Brent', 'destination': 'Customer garden',
            'purpose': 'Hedge maintenance', 'miles': '12.50', 'return_journey': 'on'})
        self.assertEqual(response.status_code, 302)
        journey = MileageJourney.objects.get()
        self.assertEqual(journey.total_miles, Decimal(25))
        self.client.post(reverse('office:mileage-review', args=['garden', journey.pk, 'approve']))
        response = self.client.post(reverse('office:mileage-generate', args=['garden']), {'month': '2025-10'})
        claim = MileageClaim.objects.get()
        self.assertRedirects(response, reverse('office:mileage-claim', args=['garden',claim.pk]))
        self.assertEqual(claim.total, Decimal('11.25'))
        self.client.force_login(self.owner)
        self.client.post(reverse('office:mileage-claim', args=['garden',claim.pk]), {'action': 'approve'})
        self.assertEqual(Expense.objects.get().amount, Decimal('11.25'))

    def test_claim_get_is_read_only_and_preview_rates_are_current(self):
        self.journey()
        claim = self.claim()
        self.journey(day=date(2026, 9, 1), miles='10000')
        self.client.force_login(self.accountant)
        response = self.client.get(reverse('office:mileage-claim', args=['garden',claim.pk]))
        self.assertContains(response, '£5.00')
        claim.refresh_from_db()
        self.assertEqual(claim.total, Decimal('11.00'))
        response = self.client.get(reverse('office:mileage-list', args=['garden']))
        self.assertContains(response, '£5.00')

    def test_get_cannot_approve_and_csrf_is_enforced(self):
        from django.test import Client
        j = self.journey(approve=False)
        url = reverse('office:mileage-review', args=['garden', j.pk, 'approve'])
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(url).status_code, 405)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.owner)
        self.assertEqual(csrf_client.post(url).status_code, 403)

    def test_bank_review_cannot_create_fuel_or_mileage_or_duplicate_reimbursement(self):
        from django.utils import timezone
        from .forms import BankExpenseReviewForm
        from .models import BankTransaction
        self.journey()
        claim = transition_claim(self.claim().pk, 'approve', self.owner)
        bank = BankTransaction.objects.create(source='monzo', external_id='monzo:reimbursement', amount_minor=-1100, transaction_at=timezone.now(), settled_at=timezone.now(), description='Pete Cookson', reference=claim.number)
        data = {'branch':'garden','supplier':'Pete Cookson','category':'office','description':'Reimbursement'}
        form = BankExpenseReviewForm(data, bank_transaction=bank)
        self.assertFalse(form.is_valid())
        self.assertIn('existing mileage claim', str(form.errors))
        bank.reference = 'unrelated'
        for category in ['mileage', 'fuel']:
            form = BankExpenseReviewForm({**data, 'category':category}, bank_transaction=bank)
            self.assertFalse(form.is_valid())
            self.assertIn('category', form.errors)
