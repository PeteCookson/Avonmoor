# Avonmoor Office: Stage 1

Private invoicing and work-record module for Avonmoor Ltd.

## Included

- Staff-only access at `/office/`.
- Customers with separate billing and property addresses.
- Completed work entries for labour, materials and waste.
- Draft invoice creation from uninvoiced work.
- Sequential invoice numbers in the format `INV-YYYY-001`.
- Immutable customer/address snapshots when an invoice is issued.
- Branded A4 PDF download with Avonmoor Ltd bank and company details.
- Issued, paid and cancelled statuses.
- Customer and invoice CSV exports for the accountant.
- No automated invoice email and no bank connection in Stage 1.

## Release steps

1. Deploy the feature branch to a Render preview service or merge it into the
   branch used by the Avonmoor Render web service.
2. Confirm `python manage.py migrate --noinput` and
   `python manage.py collectstatic --noinput` both completed during the Render
   build.
3. Create the accountant's Django user in `/admin/` and enable **Staff status**.
   Do not enable **Superuser status**.
4. Sign in and open `/office/`.
5. Enter or import customer records before issuing the first live invoice.

## Important numbering rule

The first invoice issued in each calendar year receives `INV-YYYY-001`.
Before issuing a live invoice, import the highest existing invoice number for
that year or update the `Invoice sequence` record in Django admin. This prevents
duplicate numbering when historical invoices already exist.
