import imaplib
import re
import time

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


MAILBOX_PATTERN = re.compile(
    rb'^\((?P<flags>[^)]*)\)\s+(?:"(?:[^"\\]|\\.)*"|NIL)\s+'
    rb'(?P<name>.+)$'
)


def _decode_mailbox_name(list_item):
    """Return the mailbox name from one IMAP LIST response."""

    match = MAILBOX_PATTERN.match(list_item)
    if not match:
        return None
    name = match.group('name').strip()
    if name.startswith(b'"') and name.endswith(b'"'):
        name = name[1:-1].replace(b'\\"', b'"').replace(b'\\\\', b'\\')
    return name.decode('utf-8')


def _sent_mailbox(connection):
    configured_folder = settings.EMAIL_SENT_FOLDER
    if configured_folder:
        return configured_folder

    status, mailboxes = connection.list()
    if status != 'OK' or not mailboxes:
        raise RuntimeError('The mailbox folder list could not be read.')

    fallback_names = []
    for item in mailboxes:
        if not item:
            continue
        name = _decode_mailbox_name(item)
        if not name:
            continue
        flags = {flag.lower() for flag in imaplib.ParseFlags(item)}
        if b'\\sent' in flags:
            return name
        if name.lower() in {'sent', 'sent items', 'sent messages'}:
            fallback_names.append(name)

    if fallback_names:
        return fallback_names[0]
    raise RuntimeError(
        'No Sent folder was advertised by the mailbox. Set EMAIL_SENT_FOLDER.'
    )


def _quote_mailbox_name(name):
    """Quote an IMAP mailbox name; imaplib does not quote it automatically."""

    if not name or any(char in name for char in ('\\r', '\\n', '\\x00')):
        raise ValueError('Invalid IMAP mailbox name.')
    return '"' + name.replace('\\\\', '\\\\\\\\').replace('"', '\\\\"') + '"'


def append_message_to_sent(email_message):
    """Append a complete Django email, including attachments, to IMAP Sent."""

    if not settings.EMAIL_IMAP_HOST:
        raise ImproperlyConfigured('EMAIL_IMAP_HOST is not configured.')
    if not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD:
        raise ImproperlyConfigured('Mailbox username or password is not configured.')

    connection = imaplib.IMAP4_SSL(
        settings.EMAIL_IMAP_HOST,
        settings.EMAIL_IMAP_PORT,
    )
    try:
        connection.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
        folder = _sent_mailbox(connection)
        raw_message = email_message.message().as_bytes(linesep='\r\n')
        status, _ = connection.append(
            folder,
            '(\\Seen)',
            imaplib.Time2Internaldate(time.time()),
            raw_message,
        )
        if status != 'OK':
            raise RuntimeError(f'The mailbox rejected the copy to {folder}.')
        return folder
    finally:
        try:
            connection.logout()
        except Exception:
            pass
