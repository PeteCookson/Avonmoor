# Avonmoor Office: Stages 1, 1B and 1C

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
- Automatic matching requires the exact outstanding invoice balance plus
  either the invoice number or an unambiguous customer first name, surname or
  full name. Duplicate names or multiple equal-value invoices remain in the
  review queue.
- Amount-only and otherwise ambiguous payments remain in the review queue.
- Staff can manually match an exact-balance payment, undo a match, or mark a
  payment as **Not Avonmoor** without deleting the bank record.
- Duplicate-safe Monzo CSV import remains available when OAuth is not
  configured or a manual fallback is needed.
- The integration cannot make transfers, move money or modify bank
  transactions.
- OAuth access and refresh tokens are encrypted before database storage.

## Stage 1C expense tracking

- Garden & Property and Rainwater Harvesting keep separate expense registers.
- Staff can record and edit a dated supplier cost, category, description,
  optional property/job, amount paid, payment method and reference.
- The amount is the full amount paid; the application does not calculate VAT.
- The accountant can review, edit and export expenses as CSV.
- Only the owner/superuser can void an expense. Voiding preserves the original
  record, user and timestamps for the audit trail instead of deleting it.
- Outgoing Monzo transactions are not imported. The bank connection remains
  read-only and limited to incoming payment reconciliation.

## Stage 1D operational accounting reports

- The shared **Accounting** page combines both business branches without
  merging their underlying customer, work, invoice or expense records.
- Staff can filter reports by date range and by Garden & Property, Rainwater
  Harvesting or all branches.
- The summary shows invoiced sales, invoices marked paid, active expenses,
  recorded cash position and current outstanding invoices.
- Monthly and branch comparisons use only records in the selected period.
- Current outstanding invoices include an aged-debt breakdown and direct links
  back to each invoice.
- The complete report can be exported as CSV for the accountant.
- Voided expenses and cancelled invoices are excluded.
- This is an operational report, not statutory accounts, a corporation-tax
  calculation, a VAT return or a substitute for accountant review.

## Stage 1E Monzo expense inbox

- Monzo and CSV syncs retain settled outgoing GBP transactions as well as
  incoming customer payments.
- Incoming transactions remain isolated in Payment Tracking and continue to
  use exact invoice matching rules.
- Outgoing payments enter a separate Expense Inbox and do not affect the
  accounts until a staff user reviews and records them.
- Recording an outgoing payment uses its actual settled date and amount and
  links the resulting expense back to the immutable bank transaction ID.
- A reviewed supplier can be remembered so future matching payments are
  pre-filled with the chosen branch, supplier, category and description.
- Users can exclude personal payments and internal transfers without deleting
  the bank record.
- Fuel merchants are automatically excluded because the working van is
  personally owned; vehicle costs are handled through the separate mileage log.
- Pending card authorisations remain outside the inbox until they settle.
- Monzo transaction IDs and the expense one-to-one link prevent duplicates.

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
