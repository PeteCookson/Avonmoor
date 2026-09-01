from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone


NOTIFICATION_STYLES = {
    'rainwater': {
        'accent': '#30569A',
        'accent_soft': '#EAF5FA',
        'category': 'Rainwater Harvesting',
    },
    'garden': {
        'accent': '#344C3F',
        'accent_soft': '#EDF3EF',
        'category': 'Garden & Property Maintenance',
    },
    'other': {
        'accent': '#CD7F32',
        'accent_soft': '#FFF7EF',
        'category': 'General Enquiry',
    },
}


def send_branded_notification(
    *,
    subject,
    heading,
    notification_type,
    fields,
    message='',
    message_label='Customer Message',
    reply_to=None,
    from_email=None,
    recipient_list=None,
    fail_silently=False,
):
    """Send a clear internal Avonmoor notification with a text fallback."""
    style = NOTIFICATION_STYLES[notification_type]
    cleaned_fields = [
        (label, value if value not in (None, '') else 'Not supplied')
        for label, value in fields
    ]
    received_at = timezone.localtime()
    context = {
        'heading': heading,
        'category': style['category'],
        'accent': style['accent'],
        'accent_soft': style['accent_soft'],
        'fields': cleaned_fields,
        'message': message,
        'message_label': message_label,
        'received_at': received_at,
    }
    html_body = render_to_string(
        'emails/internal_notification.html', context
    )

    text_lines = [
        heading,
        f'Service: {style["category"]}',
        f'Received: {received_at:%d %B %Y, %H:%M}',
        '',
    ]
    if message:
        text_lines.extend([message_label.upper(), message, ''])
    text_lines.append('IMPORTANT DETAILS')
    text_lines.extend(f'{label}: {value}' for label, value in cleaned_fields)

    email = EmailMultiAlternatives(
        subject=subject,
        body='\n'.join(text_lines),
        from_email=from_email or settings.EMAIL_HOST_USER,
        to=recipient_list or [settings.EMAIL_HOST_USER],
        reply_to=[reply_to] if reply_to else None,
    )
    email.attach_alternative(html_body, 'text/html')
    return email.send(fail_silently=fail_silently)
