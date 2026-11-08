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

## Mileage log and personal vehicle reimbursements

- Office → choose branch → Mileage. The ledger is Pete Cookson's personally
  owned 2004 Ford Transit Connect, not a company vehicle.
- Enter actual journey date, origin, destination, business purpose and miles;
  optional customer/property/work links must belong to the selected branch.
- Return doubles manual one-way miles. A pair of odometer readings overrides
  manual miles and represents the complete trip, without doubling.
- Staff (including the accountant) can enter/edit draft journeys, approve
  completed journeys and build a monthly branch claim. Approval locks journey
  evidence. Owner-only void actions retain the evidence.
- The tax year starts on 6 April. The first 10,000 approved business miles are
  shared across branches: 45p before 6 April 2026; 55p from that date; 25p above
  the threshold. Journeys are ordered by date then ID. Each journey is rounded
  to pence using decimal half-up rounding, with split-rate evidence retained.
- Record all earlier business mileage in the tax year before finalizing claims.
  An approval or void that would alter a later finalized claim's mileage
  allocation is rejected. Void affected unpaid claims, latest first, to correct
  earlier evidence. Paid claims remain locked and require accountant review
  outside the application for corrections; they cannot be deleted or voided.
- Build/update a monthly draft to reserve approved, unclaimed journeys. A
  database constraint prevents a journey having two active claim lines.
  The claim is always branch-specific; April can contain two tax years.
- Only an active staff superuser (owner) can approve a claim, create its linked
  mileage expense, mark it paid with a bank reference, or void an unpaid claim
  with a reason. Accountants cannot bypass owner approval through Django admin.
- Approval creates one expense under the dedicated mileage category, payable
  to Pete Cookson. No fuel expense is created. Manual fuel and mileage-category
  expenses are disabled; incoming-only Monzo matching is unchanged.
- Accounting expenses include approved claims; cash position includes mileage
  only when marked paid. The payment date is the date it is marked paid.
  Voiding preserves the original claim, lines and voided expense, then releases
  the journeys for a replacement claim. Repeated approval cannot create a
  second expense. Generated expenses are edited/voided only through claims.
- Mileage CSV contains journey evidence, vehicle ownership, branch, tax year,
  rate splits, cumulative mileage, claim/expense IDs, review/approval/payment
  audit details and void history. Formula-leading text is escaped for Excel.
- Ledger mutations use a common PostgreSQL row lock to serialize journey review,
  edits, draft generation and claim transitions. Read-only claim previews do not
  write to the ledger.
- Release uses the existing GitHub branch and `build-render.sh`, including
  migrations 0007/0008 and static collection. Both migrations add data/tables;
  they do not rewrite existing invoices, bank transactions or expenses.

### Full regression test command

```bash
DJANGO_SECRET_KEY=test EMAIL_HOST_USER=hello@example.com \
SECURE_SSL_REDIRECT=False \
STATICFILES_STORAGE=django.contrib.staticfiles.storage.StaticFilesStorage \
python manage.py test --noinput
```

The simple static storage keeps existing asset-path assertions independent of
production hashed filenames. Tests use Django's in-memory email backend; the
placeholder sender enables existing notification tests without live SMTP.

## Daily mileage entry

- The primary **Start / finish day** action opens a simplified daily form with
  date, start odometer, optional end odometer, optional multiple properties,
  editable purpose (Garden & property maintenance by default) and private miles
  defaulting to zero. No branch or return-trip question is shown on that form.
- Save a morning start reading without an end reading. The mileage list shows
  **In progress / Finish day**; the same action reopens today's existing draft.
  Incomplete days cannot be approved, allocated tax rates or included in claims.
- Finishing calculates `(end odometer − start odometer) − private miles`. Either
  selected properties or a short business route is needed for completed evidence.
  Properties are optional; multiple stops do not create multiple mileage claims.
- A database constraint permits only one active daily record per claimant/date.
  Individual journey and daily records cannot overlap through the entry forms.
  Legacy individual journeys and their original calculation remain unchanged.
- Selected stop labels are snapshotted on review so later customer/property edits
  cannot change approved claim evidence. Referenced stops prevent destructive
  property deletion. Daily readings, private miles, stops and route are included
  in evidence CSV and claim detail. Existing claim approval and payment controls
  continue to apply.
