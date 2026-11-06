# Avonmoor Office: Stages 1 and 1B

Private invoicing and work-record module for Avonmoor Ltd.

## Included

- Staff-only access at `/office/`.
- Customers with separate billing and property addresses.
- Completed work entries for labour, materials and waste.
- Draft invoice creation from uninvoiced work.
- Date-based sequential invoice numbers in the format `INV-YYYYMMDD-001`.
- Immutable customer/address snapshots when an invoice is issued.
- Branded A4 PDF download or confirmed email delivery with Avonmoor Ltd bank
  and company details.
- Issued, paid and cancelled statuses.
- Customer and invoice CSV exports for the accountant.
- No automated invoice email and no bank connection in Stage 1. A staff user
  must review and confirm each invoice email before it is sent.

## Stage 1B payment tracking

- Optional read-only Monzo OAuth connection. Only the owner/superuser can
  authorise or disconnect the bank account.
- Incoming GBP transactions only; spending transactions are not stored.
- Automatic matching requires both the exact invoice number in the payment
  data and the exact outstanding invoice balance.
- Amount-only and otherwise ambiguous payments remain in the review queue.
- Staff can manually match an exact-balance payment, undo a match, or mark a
  payment as **Not Avonmoor** without deleting the bank record.
- Duplicate-safe Monzo CSV import remains available when OAuth is not
  configured or a manual fallback is needed.
- The integration cannot make transfers, move money or modify bank
  transactions.
- OAuth access and refresh tokens are encrypted before database storage.

### Monzo setup

Create a confidential client in Monzo developer tools and configure these
Render environment variables:

- `MONZO_CLIENT_ID`
- `MONZO_CLIENT_SECRET`
- `MONZO_REDIRECT_URI=https://www.avonmoor.co.uk/office/payments/monzo/callback/`

Deploy the environment-variable change, then use **Office → Payments → Connect
Monzo**. Select only the Avonmoor account. The application registers a webhook
for live transaction updates and also provides a manual **Sync now** action.

## Release steps

1. Deploy the feature branch to a Render preview service or merge it into the
   branch used by the Avonmoor Render web service.
2. Confirm `python manage.py migrate --noinput` and
   `python manage.py collectstatic --noinput` both completed during the Render
   build.
3. Create the accountant's Django user in `/admin/` and enable **Staff status**.
   Do not enable **Superuser status** and do not assign individual Django model
   permissions. Staff status grants access to Office; destructive property
   deletion remains restricted to the owner/superuser account.
4. Sign in and open `/office/`.
5. Enter or import customer records before issuing the first live invoice.

## Important numbering rule

Invoice numbers use the invoice date plus a sequential annual suffix, for
example `INV-20261102-001`.
Before issuing a live invoice, import the highest existing invoice number for
that year or update the `Invoice sequence` record in Django admin. This prevents
duplicate numbering when historical invoices already exist.
