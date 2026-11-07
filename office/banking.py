import csv
import hashlib
import io
import json
import re
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import (
    BankConnection,
    BankTransaction,
    Customer,
    Expense,
    ExpenseImportRule,
    Invoice,
    PaymentMatch,
)


class MonzoAPIError(RuntimeError):
    def __init__(self, message, *, status_code=None):
        super().__init__(message)
        self.status_code = status_code


def monzo_configured():
    return bool(
        settings.MONZO_CLIENT_ID
        and settings.MONZO_CLIENT_SECRET
        and settings.MONZO_REDIRECT_URI
    )


def _monzo_request(method, path, *, token='', data=None, params=None):
    headers = {'Accept': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    try:
        response = requests.request(
            method,
            f'{settings.MONZO_API_BASE_URL}{path}',
            headers=headers,
            data=data,
            params=params,
            timeout=20,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        detail = ''
        status_code = None
        if getattr(error, 'response', None) is not None:
            status_code = error.response.status_code
            try:
                detail = error.response.json().get('message', '')
            except (ValueError, AttributeError):
                detail = ''
        raise MonzoAPIError(
            detail or 'Monzo could not complete the request.',
            status_code=status_code,
        ) from error
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError as error:
        raise MonzoAPIError('Monzo returned an invalid response.') from error


def exchange_authorization_code(code):
    return _monzo_request(
        'POST',
        '/oauth2/token',
        data={
            'grant_type': 'authorization_code',
            'client_id': settings.MONZO_CLIENT_ID,
            'client_secret': settings.MONZO_CLIENT_SECRET,
            'redirect_uri': settings.MONZO_REDIRECT_URI,
            'code': code,
        },
    )


def refresh_connection(connection):
    payload = _monzo_request(
        'POST',
        '/oauth2/token',
        data={
            'grant_type': 'refresh_token',
            'client_id': settings.MONZO_CLIENT_ID,
            'client_secret': settings.MONZO_CLIENT_SECRET,
            'refresh_token': connection.refresh_token(),
        },
    )
    connection.set_tokens(
        payload['access_token'], payload.get('refresh_token', '')
    )
    connection.token_expires_at = timezone.now() + timedelta(
        seconds=payload.get('expires_in', 21600)
    )
    connection.save(
        update_fields=[
            'access_token_encrypted',
            'refresh_token_encrypted',
            'token_expires_at',
            'updated_at',
        ]
    )
    return connection.access_token()


def connection_token(connection):
    if (
        connection.token_expires_at
        and connection.token_expires_at <= timezone.now() + timedelta(minutes=2)
    ):
        if not connection.refresh_token_encrypted:
            raise MonzoAPIError('The Monzo connection has expired. Reconnect it.')
        return refresh_connection(connection)
    return connection.access_token()


def list_monzo_accounts(connection):
    return _monzo_request(
        'GET', '/accounts', token=connection_token(connection)
    ).get('accounts', [])


def register_monzo_webhook(connection, callback_url):
    payload = _monzo_request(
        'POST',
        '/webhooks',
        token=connection_token(connection),
        data={'account_id': connection.account_id, 'url': callback_url},
    )
    return payload.get('webhook', {}).get('id', '')


def delete_monzo_webhook(connection):
    if connection.webhook_id:
        _monzo_request(
            'DELETE',
            f'/webhooks/{connection.webhook_id}',
            token=connection_token(connection),
        )


def logout_monzo(connection):
    _monzo_request(
        'POST', '/oauth2/logout', token=connection_token(connection)
    )


def fetch_monzo_transaction(connection, transaction_id):
    return _monzo_request(
        'GET',
        f'/transactions/{transaction_id}',
        token=connection_token(connection),
    ).get('transaction', {})


def _aware_datetime(value):
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed is None:
        raise ValidationError(f'Invalid transaction date: {value}')
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, dt_timezone.utc)
    return parsed


def _reference_text(payload):
    values = [payload.get('notes', '')]
    metadata = payload.get('metadata') or {}
    values.extend(str(value) for value in metadata.values() if value)
    return ' · '.join(value.strip() for value in values if str(value).strip())[:300]


def import_monzo_transaction(payload, account_id=''):
    external_source_id = payload.get('id')
    if not external_source_id:
        raise ValidationError('A Monzo transaction ID is required.')
    defaults = {
        'source': BankTransaction.Source.MONZO,
        'account_id': payload.get('account_id') or account_id,
        'amount_minor': int(payload.get('amount', 0)),
        'currency': (payload.get('currency') or 'GBP').upper(),
        'transaction_at': _aware_datetime(payload.get('created')),
        'settled_at': _aware_datetime(payload.get('settled')),
        'description': str(payload.get('description') or '')[:300],
        'reference': _reference_text(payload),
        'raw_data': payload,
    }
    return BankTransaction.objects.update_or_create(
        external_id=f'monzo:{external_source_id}', defaults=defaults
    )


FUEL_TRANSACTION_PATTERN = re.compile(
    r'\b(?:bp|esso|fuel|gulf|jet|petrol|shell|texaco|diesel)\b',
    re.IGNORECASE,
)


def is_fuel_transaction(bank_transaction):
    """Keep personally owned vehicle fuel outside company expenses."""

    if not bank_transaction.is_outgoing:
        return False
    text = ' '.join(
        [
            bank_transaction.description or '',
            bank_transaction.reference or '',
            str((bank_transaction.raw_data or {}).get('merchant', '')),
        ]
    )
    return bool(FUEL_TRANSACTION_PATTERN.search(text))


def expense_rule_for_transaction(bank_transaction):
    """Return the most specific active recurring-supplier rule."""

    text = ' '.join(
        [bank_transaction.description or '', bank_transaction.reference or '']
    ).casefold()
    matches = [
        rule
        for rule in ExpenseImportRule.objects.filter(active=True)
        if rule.match_text.casefold() in text
    ]
    return max(matches, key=lambda rule: len(rule.match_text), default=None)


def expense_suggestion(bank_transaction):
    """Suggest editable expense fields without posting to the ledger."""

    rule = expense_rule_for_transaction(bank_transaction)
    supplier = (bank_transaction.description or 'Monzo payment').strip()[:160]
    return {
        'rule': rule,
        'branch': rule.branch if rule else '',
        'supplier': rule.supplier if rule else supplier,
        'category': rule.category if rule else Expense.Category.OTHER,
        'description': rule.description if rule else supplier,
        'reference': (bank_transaction.reference or '')[:160],
    }


def invoice_outstanding_minor(invoice):
    matched_minor = sum(
        payment.transaction.amount_minor
        for payment in invoice.payment_matches.select_related('transaction')
    )
    return int((invoice.total * 100).quantize(Decimal('1'))) - matched_minor


def match_payment(bank_transaction, invoice, *, method, user=None):
    with db_transaction.atomic():
        bank_transaction = BankTransaction.objects.select_for_update().get(
            pk=bank_transaction.pk
        )
        invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
        if hasattr(bank_transaction, 'payment_match'):
            raise ValidationError('This bank transaction is already matched.')
        if bank_transaction.ignored_at:
            raise ValidationError('Restore this transaction before matching it.')
        if not bank_transaction.is_incoming:
            raise ValidationError('Only incoming GBP payments can be matched.')
        if invoice.status not in (Invoice.Status.ISSUED, Invoice.Status.PAID):
            raise ValidationError(
                'Only an issued or previously paid invoice can receive a bank match.'
            )
        if bank_transaction.amount_minor != invoice_outstanding_minor(invoice):
            raise ValidationError(
                'The payment must exactly equal the invoice outstanding balance.'
            )
        payment_match = PaymentMatch.objects.create(
            transaction=bank_transaction,
            invoice=invoice,
            method=method,
            matched_by=user,
        )
        if invoice.status == Invoice.Status.ISSUED:
            invoice.status = Invoice.Status.PAID
            invoice.paid_at = (
                bank_transaction.settled_at
                or bank_transaction.transaction_at
                or timezone.now()
            )
            invoice.save(update_fields=['status', 'paid_at', 'updated_at'])
        return payment_match


_CUSTOMER_NAME_STOP_WORDS = {
    'AND',
    'DR',
    'MISS',
    'MR',
    'MRS',
    'MS',
    'THE',
}


def _normalised_words(value):
    return re.findall(r'[A-Z0-9]+', str(value or '').upper())


def _contains_words(search_words, candidate_words):
    if not candidate_words or len(candidate_words) > len(search_words):
        return False
    width = len(candidate_words)
    return any(
        search_words[index:index + width] == candidate_words
        for index in range(len(search_words) - width + 1)
    )


def _customer_name_invoice_candidates(searchable, invoices):
    """Return exact-balance invoices identified unambiguously by customer name."""
    search_words = _normalised_words(searchable)
    customers = list(Customer.objects.only('id', 'display_name'))

    # Prefer a complete customer name. It is stronger than a single first name
    # or surname, but must still identify just one customer in the database.
    full_name_customer_ids = {
        customer.pk
        for customer in customers
        if _contains_words(search_words, _normalised_words(customer.display_name))
    }
    if len(full_name_customer_ids) == 1:
        customer_id = next(iter(full_name_customer_ids))
        return [
            invoice for invoice in invoices if invoice.customer_id == customer_id
        ]

    # Old references often contain only a first name or surname. A single name
    # is accepted only when it belongs to one customer across the entire ledger.
    token_owners = {}
    for customer in customers:
        tokens = {
            token
            for token in _normalised_words(customer.display_name)
            if len(token) >= 3 and token not in _CUSTOMER_NAME_STOP_WORDS
        }
        for token in tokens:
            token_owners.setdefault(token, set()).add(customer.pk)

    identified_customer_ids = {
        next(iter(owner_ids))
        for token, owner_ids in token_owners.items()
        if len(owner_ids) == 1 and token in search_words
    }
    if len(identified_customer_ids) != 1:
        return []
    customer_id = next(iter(identified_customer_ids))
    return [invoice for invoice in invoices if invoice.customer_id == customer_id]


def auto_match_transaction(bank_transaction):
    if (
        not bank_transaction.is_incoming
        or bank_transaction.ignored_at
        or hasattr(bank_transaction, 'payment_match')
    ):
        return None
    invoice_searchable = ' '.join(
        [
            bank_transaction.description,
            bank_transaction.reference,
            json.dumps(bank_transaction.raw_data, sort_keys=True),
        ]
    )
    name_searchable = ' '.join(
        [bank_transaction.description, bank_transaction.reference]
    )
    exact_balance_invoices = []
    for invoice in Invoice.objects.filter(
        status__in=(Invoice.Status.ISSUED, Invoice.Status.PAID),
        number__isnull=False,
    ).select_related('customer').prefetch_related(
        'lines', 'payment_matches__transaction'
    ):
        if bank_transaction.amount_minor == invoice_outstanding_minor(invoice):
            exact_balance_invoices.append(invoice)

    invoice_number_candidates = []
    for invoice in exact_balance_invoices:
        pattern = rf'(?<![A-Z0-9]){re.escape(invoice.number.upper())}(?![A-Z0-9])'
        if re.search(pattern, invoice_searchable.upper()):
            invoice_number_candidates.append(invoice)
    if len(invoice_number_candidates) == 1:
        invoice = invoice_number_candidates[0]
    else:
        name_candidates = _customer_name_invoice_candidates(
            name_searchable, exact_balance_invoices
        )
        if len(name_candidates) != 1:
            return None
        invoice = name_candidates[0]

    if invoice not in exact_balance_invoices:
        return None
    return match_payment(
        bank_transaction,
        invoice,
        method=PaymentMatch.Method.AUTOMATIC,
    )


def retry_auto_matching():
    """Re-evaluate review payments after invoices or matching rules change."""
    matched = 0
    transactions = BankTransaction.objects.filter(
        amount_minor__gt=0,
        currency='GBP',
        ignored_at__isnull=True,
        payment_match__isnull=True,
    ).order_by('transaction_at', 'pk')
    for bank_transaction in transactions:
        if auto_match_transaction(bank_transaction):
            matched += 1
    return matched


def sync_monzo_transactions(connection):
    token = connection_token(connection)
    since = (
        connection.last_synced_at - timedelta(days=7)
        if connection.last_synced_at
        else timezone.now() - timedelta(days=90)
    )
    imported = 0
    matched = 0
    cursor = since
    for _ in range(100):
        payload = _monzo_request(
            'GET',
            '/transactions',
            token=token,
            params={
                'account_id': connection.account_id,
                'since': cursor.isoformat(),
                'limit': 100,
            },
        )
        rows = payload.get('transactions', [])
        if not rows:
            break
        rows.sort(key=lambda item: item.get('created', ''))
        for row in rows:
            if (
                int(row.get('amount', 0)) == 0
                or (row.get('currency') or 'GBP').upper() != 'GBP'
            ):
                continue
            bank_transaction, created = import_monzo_transaction(
                row, connection.account_id
            )
            imported += int(created)
            if auto_match_transaction(bank_transaction):
                matched += 1
        if len(rows) < 100:
            break
        newest = _aware_datetime(rows[-1].get('created'))
        if not newest or newest <= cursor:
            break
        cursor = newest + timedelta(microseconds=1)
    connection.last_synced_at = timezone.now()
    connection.save(update_fields=['last_synced_at', 'updated_at'])
    matched += retry_auto_matching()
    return imported, matched


def _csv_value(row, *names):
    lowered = {str(key).strip().lower(): value for key, value in row.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value not in (None, ''):
            return str(value).strip()
    return ''


def _csv_datetime(date_value, time_value=''):
    combined = f'{date_value} {time_value}'.strip()
    parsed = parse_datetime(combined)
    if parsed is None:
        for date_format in (
            '%d/%m/%Y %H:%M:%S',
            '%d/%m/%Y %H:%M',
            '%d/%m/%Y',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d',
        ):
            try:
                parsed = datetime.strptime(combined, date_format)
                break
            except ValueError:
                continue
    if parsed is None:
        raise ValidationError(f'Could not read transaction date “{combined}”.')
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def import_bank_csv(uploaded_file):
    if uploaded_file.size > 2 * 1024 * 1024:
        raise ValidationError('The CSV file must be smaller than 2 MB.')
    try:
        text = uploaded_file.read().decode('utf-8-sig')
    except UnicodeDecodeError as error:
        raise ValidationError('The CSV file must use UTF-8 encoding.') from error
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValidationError('The CSV file has no header row.')
    imported = duplicates = matched = 0
    for row_number, row in enumerate(reader, start=2):
        amount_value = _csv_value(row, 'Amount', 'Amount (GBP)')
        date_value = _csv_value(row, 'Date', 'Created', 'Transaction date')
        if not amount_value or not date_value:
            raise ValidationError(
                f'Row {row_number} needs at least Date and Amount values.'
            )
        try:
            amount_minor = int(
                (Decimal(amount_value.replace(',', '')) * 100).quantize(
                    Decimal('1'), rounding=ROUND_HALF_UP
                )
            )
        except InvalidOperation as error:
            raise ValidationError(
                f'Row {row_number} has an invalid amount.'
            ) from error
        currency = (_csv_value(row, 'Currency') or 'GBP').upper()
        if amount_minor == 0 or currency != 'GBP':
            continue
        transaction_at = _csv_datetime(
            date_value, _csv_value(row, 'Time')
        )
        supplied_id = _csv_value(row, 'Transaction ID', 'ID')
        fingerprint = supplied_id or hashlib.sha256(
            json.dumps(row, sort_keys=True, default=str).encode('utf-8')
        ).hexdigest()
        description = _csv_value(row, 'Name', 'Description', 'Counterparty')
        reference = _csv_value(
            row, 'Reference', 'Notes and #tags', 'Notes', 'Memo'
        )
        bank_transaction, created = BankTransaction.objects.get_or_create(
            external_id=f'csv:{fingerprint}',
            defaults={
                'source': BankTransaction.Source.CSV,
                'amount_minor': amount_minor,
                'currency': currency,
                'transaction_at': transaction_at,
                'settled_at': transaction_at,
                'description': description[:300],
                'reference': reference[:300],
                'raw_data': row,
            },
        )
        if created:
            imported += 1
            if auto_match_transaction(bank_transaction):
                matched += 1
        else:
            duplicates += 1
    return imported, duplicates, matched
