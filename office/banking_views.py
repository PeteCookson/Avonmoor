import json
import logging
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from .banking import (
    MonzoAPIError,
    auto_match_transaction,
    delete_monzo_webhook,
    exchange_authorization_code,
    fetch_monzo_transaction,
    import_bank_csv,
    import_monzo_transaction,
    list_monzo_accounts,
    logout_monzo,
    match_payment,
    monzo_configured,
    register_monzo_webhook,
    sync_monzo_transactions,
    is_fuel_transaction,
)
from .forms import (
    BankCSVImportForm,
    BankExpenseReviewForm,
    MonzoAccountForm,
    PaymentMatchForm,
)
from .models import (
    BankConnection,
    BankTransaction,
    Expense,
    ExpenseImportRule,
    PaymentMatch,
)
from .views import OfficeAccessMixin, OwnerOnlyMixin


logger = logging.getLogger(__name__)


class PaymentsView(OfficeAccessMixin, View):
    template_name = 'office/payments.html'

    def get(self, request):
        connection = BankConnection.objects.filter(provider='monzo').first()
        transactions = BankTransaction.objects.filter(
            amount_minor__gt=0, currency='GBP'
        ).select_related(
            'payment_match__invoice__customer', 'ignored_by'
        )
        status = request.GET.get('status', 'review')
        if status == 'matched':
            transactions = transactions.filter(payment_match__isnull=False)
        elif status == 'ignored':
            transactions = transactions.filter(ignored_at__isnull=False)
        elif status == 'all':
            pass
        else:
            status = 'review'
            transactions = transactions.filter(
                payment_match__isnull=True, ignored_at__isnull=True
            )
        base = BankTransaction.objects.filter(amount_minor__gt=0, currency='GBP')
        context = {
            'connection': connection,
            'connection_pending': bool(
                connection
                and not connection.active
                and connection.access_token_encrypted
            ),
            'monzo_configured': monzo_configured(),
            'callback_url': settings.MONZO_REDIRECT_URI,
            'transactions': transactions[:150],
            'status_filter': status,
            'review_count': base.filter(
                payment_match__isnull=True, ignored_at__isnull=True
            ).count(),
            'matched_count': base.filter(payment_match__isnull=False).count(),
            'ignored_count': base.filter(ignored_at__isnull=False).count(),
            'csv_form': BankCSVImportForm(),
        }
        return render(request, self.template_name, context)


class ExpenseInboxView(OfficeAccessMixin, View):
    template_name = 'office/expense_inbox.html'

    def get(self, request):
        outgoing = list(
            BankTransaction.objects.filter(
                amount_minor__lt=0,
                currency='GBP',
                settled_at__isnull=False,
            )
            .select_related('expense_record', 'ignored_by')[:500]
        )
        status = request.GET.get('status', 'review')
        if status not in {'review', 'recorded', 'excluded', 'all'}:
            status = 'review'

        def transaction_state(bank_transaction):
            if hasattr(bank_transaction, 'expense_record'):
                return 'recorded'
            if bank_transaction.ignored_at or is_fuel_transaction(bank_transaction):
                return 'excluded'
            return 'review'

        for bank_transaction in outgoing:
            bank_transaction.expense_state = transaction_state(bank_transaction)
            bank_transaction.fuel_excluded = is_fuel_transaction(bank_transaction)
        counts = {
            state: sum(
                transaction.expense_state == state for transaction in outgoing
            )
            for state in ('review', 'recorded', 'excluded')
        }
        transactions = (
            outgoing
            if status == 'all'
            else [
                transaction
                for transaction in outgoing
                if transaction.expense_state == status
            ]
        )
        return render(
            request,
            self.template_name,
            {
                'transactions': transactions,
                'status_filter': status,
                **{f'{key}_count': value for key, value in counts.items()},
            },
        )


class BankExpenseReviewView(OfficeAccessMixin, View):
    template_name = 'office/expense_bank_review.html'

    def get_transaction(self, pk):
        return get_object_or_404(
            BankTransaction.objects.select_related('expense_record'),
            pk=pk,
            amount_minor__lt=0,
            currency='GBP',
            settled_at__isnull=False,
        )

    def get(self, request, pk):
        bank_transaction = self.get_transaction(pk)
        if hasattr(bank_transaction, 'expense_record'):
            messages.info(request, 'This payment is already recorded as an expense.')
            return redirect('office:expense-inbox')
        if bank_transaction.ignored_at or is_fuel_transaction(bank_transaction):
            messages.warning(request, 'This payment is excluded from expenses.')
            return redirect('office:expense-inbox')
        return render(
            request,
            self.template_name,
            {
                'bank_transaction': bank_transaction,
                'form': BankExpenseReviewForm(
                    bank_transaction=bank_transaction
                ),
            },
        )

    def post(self, request, pk):
        with transaction.atomic():
            bank_transaction = get_object_or_404(
                BankTransaction.objects.select_for_update(),
                pk=pk,
                amount_minor__lt=0,
                currency='GBP',
                settled_at__isnull=False,
            )
            if hasattr(bank_transaction, 'expense_record'):
                messages.info(
                    request, 'This payment is already recorded as an expense.'
                )
                return redirect('office:expense-inbox')
            form = BankExpenseReviewForm(
                request.POST, bank_transaction=bank_transaction
            )
            if form.is_valid():
                expense = Expense(
                    branch=form.cleaned_data['branch'],
                    expense_date=(
                        bank_transaction.settled_at
                        or bank_transaction.transaction_at
                    ).date(),
                    supplier=form.cleaned_data['supplier'],
                    category=form.cleaned_data['category'],
                    description=form.cleaned_data['description'],
                    property=form.cleaned_data['property'],
                    amount=abs(bank_transaction.amount),
                    payment_method=Expense.PaymentMethod.BANK,
                    reference=form.cleaned_data['reference'],
                    notes=form.cleaned_data['notes'],
                    bank_transaction=bank_transaction,
                    created_by=request.user,
                    updated_by=request.user,
                )
                expense.full_clean()
                expense.save()
                if form.cleaned_data['remember_supplier']:
                    match_text = (
                        bank_transaction.description
                        or bank_transaction.reference
                    ).strip()[:160]
                    if match_text:
                        rule, created = ExpenseImportRule.objects.get_or_create(
                            match_text=match_text,
                            defaults={
                                'branch': expense.branch,
                                'supplier': expense.supplier,
                                'category': expense.category,
                                'description': expense.description,
                                'created_by': request.user,
                                'updated_by': request.user,
                            },
                        )
                        if not created:
                            rule.branch = expense.branch
                            rule.supplier = expense.supplier
                            rule.category = expense.category
                            rule.description = expense.description
                            rule.active = True
                            rule.updated_by = request.user
                            rule.save()
                messages.success(
                    request,
                    'Expense recorded from Monzo without changing the bank transaction.',
                )
                return redirect('office:expense-inbox')
        return render(
            request,
            self.template_name,
            {'bank_transaction': bank_transaction, 'form': form},
        )


class BankExpenseIgnoreView(OfficeAccessMixin, View):
    def post(self, request, pk):
        bank_transaction = get_object_or_404(
            BankTransaction,
            pk=pk,
            amount_minor__lt=0,
            currency='GBP',
            settled_at__isnull=False,
        )
        if not hasattr(bank_transaction, 'expense_record'):
            bank_transaction.ignored_at = timezone.now()
            bank_transaction.ignored_by = request.user
            bank_transaction.save(
                update_fields=['ignored_at', 'ignored_by', 'updated_at']
            )
            messages.success(request, 'Payment excluded from business expenses.')
        return redirect('office:expense-inbox')


class BankExpenseRestoreView(OfficeAccessMixin, View):
    def post(self, request, pk):
        bank_transaction = get_object_or_404(
            BankTransaction,
            pk=pk,
            amount_minor__lt=0,
            currency='GBP',
            settled_at__isnull=False,
        )
        if is_fuel_transaction(bank_transaction):
            messages.warning(
                request,
                'Fuel remains excluded because the van is personally owned.',
            )
        elif not hasattr(bank_transaction, 'expense_record'):
            bank_transaction.ignored_at = None
            bank_transaction.ignored_by = None
            bank_transaction.save(
                update_fields=['ignored_at', 'ignored_by', 'updated_at']
            )
            messages.success(request, 'Payment returned to expense review.')
        return redirect('office:expense-inbox')


class MonzoConnectView(OwnerOnlyMixin, View):
    def post(self, request):
        if not monzo_configured():
            messages.error(
                request,
                'Add the Monzo client ID, secret and callback URL before connecting.',
            )
            return redirect('office:payments')
        state = secrets.token_urlsafe(32)
        request.session['monzo_oauth_state'] = state
        query = urlencode(
            {
                'client_id': settings.MONZO_CLIENT_ID,
                'redirect_uri': settings.MONZO_REDIRECT_URI,
                'response_type': 'code',
                'state': state,
            }
        )
        return HttpResponseRedirect(f'{settings.MONZO_AUTHORIZE_URL}?{query}')


class MonzoCallbackView(OwnerOnlyMixin, View):
    def get(self, request):
        expected_state = request.session.pop('monzo_oauth_state', '')
        if not expected_state or not secrets.compare_digest(
            request.GET.get('state', ''), expected_state
        ):
            messages.error(request, 'The Monzo connection could not be verified.')
            return redirect('office:payments')
        code = request.GET.get('code', '')
        if not code:
            messages.error(request, 'Monzo did not return an authorisation code.')
            return redirect('office:payments')
        try:
            payload = exchange_authorization_code(code)
        except MonzoAPIError as error:
            messages.error(request, str(error))
            return redirect('office:payments')
        connection, _ = BankConnection.objects.get_or_create(
            provider='monzo', defaults={'connected_by': request.user}
        )
        connection.connected_by = request.user
        connection.account_id = ''
        connection.account_name = ''
        connection.active = False
        connection.webhook_id = ''
        connection.set_tokens(
            payload['access_token'], payload.get('refresh_token', '')
        )
        connection.token_expires_at = timezone.now() + timedelta(
            seconds=payload.get('expires_in', 21600)
        )
        connection.save()
        messages.info(
            request,
            'Email confirmed. Approve Avonmoor Office in the Monzo app, '
            'then select Continue setup.',
        )
        return redirect('office:payments')


class MonzoAccountView(OwnerOnlyMixin, View):
    template_name = 'office/monzo_account.html'

    def get_connection(self):
        return get_object_or_404(BankConnection, provider='monzo')

    def accounts(self, request, connection):
        try:
            return list_monzo_accounts(connection)
        except MonzoAPIError as error:
            if error.status_code in {401, 403}:
                messages.warning(
                    request,
                    'Monzo approval is still required. Open the Monzo app, '
                    'approve Avonmoor Office, then select Continue setup.',
                )
            else:
                messages.error(request, str(error))
            return None

    def get(self, request):
        connection = self.get_connection()
        accounts = self.accounts(request, connection)
        if accounts is None:
            return redirect('office:payments')
        return render(
            request,
            self.template_name,
            {'form': MonzoAccountForm(accounts=accounts)},
        )

    def post(self, request):
        connection = self.get_connection()
        accounts = self.accounts(request, connection)
        if accounts is None:
            return redirect('office:payments')
        form = MonzoAccountForm(request.POST, accounts=accounts)
        if not form.is_valid():
            return render(request, self.template_name, {'form': form})
        account = form.selected_account()
        connection.account_id = account['id']
        connection.account_name = account.get('description') or account['id']
        connection.active = True
        connection.save(
            update_fields=['account_id', 'account_name', 'active', 'updated_at']
        )
        webhook_url = request.build_absolute_uri(
            reverse('office:monzo-webhook')
        )
        try:
            connection.webhook_id = register_monzo_webhook(
                connection, webhook_url
            )
            connection.save(update_fields=['webhook_id', 'updated_at'])
        except MonzoAPIError:
            logger.exception('Monzo webhook registration failed')
            messages.warning(
                request,
                'The account connected, but live updates could not be enabled. '
                'Use Sync now while this is corrected.',
            )
        try:
            imported, matched = sync_monzo_transactions(connection)
        except (MonzoAPIError, ValidationError):
            logger.exception('Initial Monzo sync failed')
            messages.warning(
                request,
                'The account connected, but the first transaction sync failed.',
            )
        else:
            messages.success(
                request,
                f'Monzo connected. Imported {imported} new transaction(s); '
                f'{matched} matched automatically.',
            )
        return redirect('office:payments')


class MonzoSyncView(OfficeAccessMixin, View):
    def post(self, request):
        connection = get_object_or_404(
            BankConnection, provider='monzo', active=True
        )
        try:
            imported, matched = sync_monzo_transactions(connection)
        except (MonzoAPIError, ValidationError) as error:
            logger.exception('Monzo sync failed')
            messages.error(request, f'Monzo sync failed: {error}')
        else:
            messages.success(
                request,
                f'Sync complete: {imported} new transaction(s), '
                f'{matched} matched automatically.',
            )
        return redirect('office:payments')


class MonzoDisconnectView(OwnerOnlyMixin, View):
    def post(self, request):
        connection = get_object_or_404(BankConnection, provider='monzo')
        try:
            delete_monzo_webhook(connection)
            logout_monzo(connection)
        except MonzoAPIError:
            logger.exception('Monzo remote disconnect was incomplete')
        connection.active = False
        connection.webhook_id = ''
        connection.access_token_encrypted = ''
        connection.refresh_token_encrypted = ''
        connection.token_expires_at = None
        connection.save(
            update_fields=[
                'active',
                'webhook_id',
                'access_token_encrypted',
                'refresh_token_encrypted',
                'token_expires_at',
                'updated_at',
            ]
        )
        messages.success(
            request,
            'Monzo disconnected. Imported payment history has been retained.',
        )
        return redirect('office:payments')


class BankCSVImportView(OfficeAccessMixin, View):
    def post(self, request):
        form = BankCSVImportForm(request.POST, request.FILES)
        if not form.is_valid():
            messages.error(request, '; '.join(form.errors['csv_file']))
            return redirect('office:payments')
        try:
            imported, duplicates, matched = import_bank_csv(
                form.cleaned_data['csv_file']
            )
        except ValidationError as error:
            messages.error(request, '; '.join(error.messages))
        else:
            messages.success(
                request,
                f'CSV import complete: {imported} new transaction(s), '
                f'{duplicates} duplicate(s), {matched} matched automatically.',
            )
        return redirect('office:payments')


class PaymentMatchView(OfficeAccessMixin, View):
    template_name = 'office/payment_match.html'

    def get_transaction(self, pk):
        return get_object_or_404(
            BankTransaction.objects.select_related('payment_match'), pk=pk
        )

    def get(self, request, pk):
        bank_transaction = self.get_transaction(pk)
        if hasattr(bank_transaction, 'payment_match'):
            messages.warning(request, 'This payment is already matched.')
            return redirect('office:payments')
        return render(
            request,
            self.template_name,
            {
                'bank_transaction': bank_transaction,
                'form': PaymentMatchForm(bank_transaction=bank_transaction),
            },
        )

    def post(self, request, pk):
        bank_transaction = self.get_transaction(pk)
        form = PaymentMatchForm(
            request.POST, bank_transaction=bank_transaction
        )
        if form.is_valid():
            try:
                match_payment(
                    bank_transaction,
                    form.cleaned_data['invoice'],
                    method=PaymentMatch.Method.MANUAL,
                    user=request.user,
                )
            except ValidationError as error:
                form.add_error(None, '; '.join(error.messages))
            else:
                messages.success(request, 'Payment matched and invoice marked paid.')
                return redirect('office:payments')
        return render(
            request,
            self.template_name,
            {'bank_transaction': bank_transaction, 'form': form},
        )


class PaymentIgnoreView(OfficeAccessMixin, View):
    def post(self, request, pk):
        bank_transaction = get_object_or_404(BankTransaction, pk=pk)
        if not hasattr(bank_transaction, 'payment_match'):
            bank_transaction.ignored_at = timezone.now()
            bank_transaction.ignored_by = request.user
            bank_transaction.save(
                update_fields=['ignored_at', 'ignored_by', 'updated_at']
            )
            messages.success(request, 'Payment marked as not Avonmoor.')
        return redirect('office:payments')


class PaymentRestoreView(OfficeAccessMixin, View):
    def post(self, request, pk):
        bank_transaction = get_object_or_404(BankTransaction, pk=pk)
        bank_transaction.ignored_at = None
        bank_transaction.ignored_by = None
        bank_transaction.save(
            update_fields=['ignored_at', 'ignored_by', 'updated_at']
        )
        auto_match_transaction(bank_transaction)
        messages.success(request, 'Payment returned to the review queue.')
        return redirect('office:payments')


class PaymentUnmatchView(OfficeAccessMixin, View):
    def post(self, request, pk):
        payment_match = get_object_or_404(
            PaymentMatch.objects.select_related('invoice'), pk=pk
        )
        invoice = payment_match.invoice
        payment_match.delete()
        if invoice.status == invoice.Status.PAID:
            invoice.status = invoice.Status.ISSUED
            invoice.paid_at = None
            invoice.save(update_fields=['status', 'paid_at', 'updated_at'])
        messages.success(request, 'Bank match removed and invoice reopened.')
        return redirect('office:payments')


@method_decorator(csrf_exempt, name='dispatch')
class MonzoWebhookView(View):
    http_method_names = ['post']

    def post(self, request):
        if len(request.body) > 256 * 1024:
            return HttpResponse(status=413)
        try:
            event = json.loads(request.body.decode('utf-8'))
            data = event.get('data') or {}
            transaction_id = data.get('id')
            account_id = data.get('account_id')
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            return HttpResponse(status=400)
        if event.get('type') != 'transaction.created' or not transaction_id:
            return HttpResponse(status=202)
        connection = BankConnection.objects.filter(
            provider='monzo', active=True, account_id=account_id
        ).first()
        if not connection:
            return HttpResponse(status=202)
        try:
            verified = fetch_monzo_transaction(connection, transaction_id)
            if (
                verified.get('account_id') != connection.account_id
                or int(verified.get('amount', 0)) == 0
                or (verified.get('currency') or 'GBP').upper() != 'GBP'
            ):
                return HttpResponse(status=202)
            bank_transaction, _ = import_monzo_transaction(
                verified, connection.account_id
            )
            auto_match_transaction(bank_transaction)
        except (MonzoAPIError, ValidationError, ValueError, TypeError):
            logger.exception('Verified Monzo webhook processing failed')
        return HttpResponse(status=202)
