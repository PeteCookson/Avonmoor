import base64
import re
from io import BytesIO
from pathlib import Path

import reportlab
from django.conf import settings
from django.utils.formats import date_format
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


DEEP_GREEN = colors.HexColor('#0B4540')
LEAF = colors.HexColor('#3E7A45')
COPPER = colors.HexColor('#CD7F32')
PALE_GREEN = colors.HexColor('#EEF4EA')
WARM_PAPER = colors.HexColor('#F7F5F0')
GREY = colors.HexColor('#878583')
LINE = colors.HexColor('#D7D7D3')

REPORTLAB_FONTS = Path(reportlab.__file__).resolve().parent / 'fonts'
pdfmetrics.registerFont(TTFont('AvonmoorSans', REPORTLAB_FONTS / 'Vera.ttf'))
pdfmetrics.registerFont(TTFont('AvonmoorSans-Bold', REPORTLAB_FONTS / 'VeraBd.ttf'))


def _logo_bytes():
    logo_path = Path(settings.BASE_DIR) / (
        'contact/static/img/avonmoor-master-horizontal-light.svg'
    )
    svg = logo_path.read_text(encoding='utf-8')
    match = re.search(r'base64,([^"\']+)', svg)
    if not match:
        return None
    return base64.b64decode(match.group(1))


def _money(value):
    return f'£{value:,.2f}'


def _address_lines(snapshot):
    return [
        value
        for value in (
            snapshot.get('display_name'),
            snapshot.get('contact_name'),
            snapshot.get('billing_address_1'),
            snapshot.get('billing_address_2'),
            snapshot.get('town'),
            snapshot.get('county'),
            snapshot.get('postcode'),
        )
        if value
    ]


def build_invoice_pdf(invoice):
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=17 * mm,
        rightMargin=17 * mm,
        topMargin=14 * mm,
        bottomMargin=18 * mm,
        title=f'Invoice {invoice.display_number}',
        author='Avonmoor Ltd',
    )
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        'Body',
        parent=styles['BodyText'],
        fontName='AvonmoorSans',
        fontSize=9.5,
        leading=13,
        textColor=DEEP_GREEN,
    )
    small = ParagraphStyle(
        'Small', parent=body, fontSize=8, leading=11, textColor=GREY
    )
    label = ParagraphStyle(
        'Label',
        parent=body,
        fontSize=8,
        leading=10,
        fontName='AvonmoorSans-Bold',
        textColor=LEAF,
        spaceAfter=3,
    )
    title = ParagraphStyle(
        'InvoiceTitle',
        parent=body,
        fontName='Times-Roman',
        fontSize=30,
        leading=34,
        textColor=DEEP_GREEN,
    )
    right = ParagraphStyle('Right', parent=body, alignment=TA_RIGHT)
    table_text = ParagraphStyle('TableText', parent=body, fontSize=8.5, leading=11)
    table_right = ParagraphStyle(
        'TableRight', parent=table_text, alignment=TA_RIGHT
    )
    table_header = ParagraphStyle(
        'TableHeader',
        parent=table_text,
        fontName='AvonmoorSans-Bold',
        textColor=colors.white,
    )
    table_header_right = ParagraphStyle(
        'TableHeaderRight', parent=table_header, alignment=TA_RIGHT
    )

    story = []
    logo_data = _logo_bytes()
    if logo_data:
        logo = Image(BytesIO(logo_data), width=101 * mm, height=38.2 * mm)
    else:
        logo = Paragraph('<b>AVONMOOR</b>', title)
    company = Paragraph(
        '<b>AVONMOOR LTD</b><br/>'
        '01364 223349<br/>'
        'hello@avonmoor.co.uk<br/>'
        'avonmoor.co.uk',
        right,
    )
    header = Table([[logo, company]], colWidths=[118 * mm, 52 * mm])
    header.setStyle(
        TableStyle(
            [
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.extend([header, Spacer(1, 3 * mm)])

    story.append(
        Table(
            [['']],
            colWidths=[176 * mm],
            rowHeights=[0.8 * mm],
            style=TableStyle([('BACKGROUND', (0, 0), (-1, -1), COPPER)]),
        )
    )
    story.append(Spacer(1, 5 * mm))

    invoice_meta = Paragraph(
        f'<b>Invoice number</b>&nbsp;&nbsp; {invoice.display_number}<br/>'
        f'<b>Invoice date</b>&nbsp;&nbsp; '
        f'{date_format(invoice.issue_date, "d/m/Y")}',
        right,
    )
    title_table = Table(
        [[Paragraph('INVOICE', title), invoice_meta]],
        colWidths=[92 * mm, 84 * mm],
    )
    title_table.setStyle(
        TableStyle(
            [
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.extend([title_table, Spacer(1, 5 * mm)])

    billing = invoice.billing_details
    bill_to = '<br/>'.join(_address_lines(billing))
    address_box = Table(
        [[Paragraph('BILL TO', label)], [Paragraph(bill_to, body)]],
        colWidths=[176 * mm],
    )
    address_box.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, -1), PALE_GREEN),
                ('LEFTPADDING', (0, 0), (-1, -1), 5 * mm),
                ('RIGHTPADDING', (0, 0), (-1, -1), 5 * mm),
                ('TOPPADDING', (0, 0), (-1, 0), 4 * mm),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 0),
                ('TOPPADDING', (0, 1), (-1, 1), 1 * mm),
                ('BOTTOMPADDING', (0, 1), (-1, 1), 4 * mm),
            ]
        )
    )
    story.extend([address_box, Spacer(1, 7 * mm)])

    rows = [
        [
            Paragraph('Date', table_header),
            Paragraph('Description', table_header),
            Paragraph('Qty', table_header_right),
            Paragraph('Rate', table_header_right),
            Paragraph('Cost', table_header_right),
        ]
    ]
    for line in invoice.lines.all():
        quantity = f'{line.quantity.normalize()} {line.get_unit_display()}'
        rows.append(
            [
                Paragraph(date_format(line.service_date, 'd/m/Y'), table_text),
                Paragraph(line.description, table_text),
                Paragraph(quantity, table_right),
                Paragraph(_money(line.unit_price), table_right),
                Paragraph(_money(line.total), table_right),
            ]
        )

    lines_table = Table(
        rows,
        repeatRows=1,
        colWidths=[24 * mm, 83 * mm, 24 * mm, 22 * mm, 23 * mm],
    )
    lines_table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), DEEP_GREEN),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('GRID', (0, 0), (-1, -1), 0.4, LINE),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, WARM_PAPER]),
                ('LEFTPADDING', (0, 0), (-1, -1), 3 * mm),
                ('RIGHTPADDING', (0, 0), (-1, -1), 3 * mm),
                ('TOPPADDING', (0, 0), (-1, -1), 3 * mm),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3 * mm),
                ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
            ]
        )
    )
    story.extend([lines_table, Spacer(1, 5 * mm)])

    total_table = Table(
        [[Paragraph('TOTAL DUE', table_header_right), Paragraph(_money(invoice.total), table_header_right)]],
        colWidths=[145 * mm, 31 * mm],
    )
    total_table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, -1), DEEP_GREEN),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
                ('LEFTPADDING', (0, 0), (-1, -1), 4 * mm),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4 * mm),
                ('TOPPADDING', (0, 0), (-1, -1), 3 * mm),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3 * mm),
            ]
        )
    )
    story.extend([total_table, Spacer(1, 6 * mm)])

    payment = KeepTogether(
        [
            Table(
                [
                    [Paragraph('PAYMENT DETAILS', ParagraphStyle('PayLabel', parent=label, textColor=COPPER))],
                    [
                        Paragraph(
                            '<b>Account name:</b> AVONMOOR LTD'
                            '&nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp;'
                            '<b>Sort code:</b> 04-00-05'
                            '&nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp;'
                            '<b>Account number:</b> 45959946',
                            body,
                        )
                    ],
                    [Paragraph('Use the invoice number as the payment reference.', small)],
                ],
                colWidths=[176 * mm],
                style=TableStyle(
                    [
                        ('BACKGROUND', (0, 0), (-1, -1), WARM_PAPER),
                        ('LEFTPADDING', (0, 0), (-1, -1), 4 * mm),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 4 * mm),
                        ('TOPPADDING', (0, 0), (-1, -1), 2.2 * mm),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.2 * mm),
                    ]
                ),
            )
        ]
    )
    story.append(payment)

    def footer(canvas, _document):
        canvas.saveState()
        canvas.setStrokeColor(COPPER)
        canvas.setLineWidth(0.7)
        canvas.line(17 * mm, 13 * mm, 193 * mm, 13 * mm)
        canvas.setFillColor(DEEP_GREEN)
        canvas.setFont('AvonmoorSans-Bold', 7.5)
        canvas.drawCentredString(
            A4[0] / 2,
            8.5 * mm,
            'Avonmoor Ltd  |  Company no. 15569989  |  Registered in England and Wales',
        )
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
