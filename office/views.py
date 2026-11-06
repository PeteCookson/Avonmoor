import csv
import logging
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.core.exceptions import PermissionDenied
from django.core.mail import EmailMessage
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Max, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import (
    CreateView,
    DetailView,
    ListView,
    UpdateView,
)

from .forms import (
    CustomerForm,
    InvoiceCreateForm,
    InvoiceEmailForm,
    InvoiceForm,
    InvoiceLineFormSet,
    PropertyForm,
    WorkEntryForm,
)
from .models import (
    BusinessBranch,
    Customer,
    Invoice,
    InvoiceEmail,
    InvoiceLine,
    Property,
    WorkEntry,
)
from .pdf import build_invoice_pdf


logger = logging.getLogger(__name__)

BRANCH_META = {
    BusinessBranch.GARDEN: {
        'label': 'Garden & Property',
        'short_label': 'Garden',
        'work_label': 'Work log',
        'record_label': 'Record work',
    },
    BusinessBranch.RAINWATER: {
        'label': 'Rainwater Harvesting',
        'short_label': 'Rainwater',
        'work_label': 'Jobs log',
        'record_label': 'Record job',
    },
}


def append_work_entries(invoice, work_entries):
    """Append linked work entries after the draft's existing invoice lines."""

    last_position = invoice.lines.aggregate(
        last_position=Max('sort_order')
    )['last_position']
    next_position = 0 if last_position is None else last_position + 1
    for offset, entry in enumerate(work_entries):
        InvoiceLine.objects.create(
            invoice=invoice,
            work_entry=entry,
            service_date=entry.service_date,
            category=entry.category,
            description=entry.description,
            quantity=entry.quantity,
            unit=entry.unit,
            unit_price=entry.unit_price,
            sort_order=next_position + offset,
        )


def available_work_entries_for_update(selected_ids):
    """Lock uninvoiced work without an outer join PostgreSQL cannot lock."""

    invoiced_work_ids = InvoiceLine.objects.filter(
        work_entry_id__isnull=False
    ).values('work_entry_id')
    return (
        WorkEntry.objects.select_for_update()
        .filter(pk__in=selected_ids)
        .exclude(pk__in=invoiced_work_ids)
        .select_related('property', 'property__customer')
        .order_by('service_date', 'pk')
    )


class OfficeAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_staff

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            raise PermissionDenied
        return super().handle_no_permission()


class OwnerOnlyMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Limit destructive Office actions to the Avonmoor owner account."""

    def test_func(self):
        return self.request.user.is_superuser

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            raise PermissionDenied
        return super().handle_no_permission()


class BranchContextMixin:
    def dispatch(self, request, *args, **kwargs):
        self.branch = kwargs.get('branch')
        if self.branch not in BusinessBranch.values:
            raise PermissionDenied
        self.branch_meta = BRANCH_META[self.branch]
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            branch=self.branch,
            branch_meta=self.branch_meta,
        )
        return context

    def branch_reverse(self, name, **kwargs):
        kwargs['branch'] = self.branch
        return reverse(f'office:{name}', kwargs=kwargs)

    def branch_context(self, **kwargs):
        return {
            'branch': self.branch,
            'branch_meta': self.branch_meta,
            **kwargs,
        }


class OfficeDashboardView(OfficeAccessMixin, View):
    template_name = 'office/branch_select.html'

    def get(self, request):
        return render(
            request,
            self.template_name,
            {'branches': BRANCH_META},
        )


class BranchDashboardView(BranchContextMixin, OfficeAccessMixin, View):
    template_name = 'office/dashboard.html'

    def get(self, request, branch):
        line_total = ExpressionWrapper(
            F('lines__quantity') * F('lines__unit_price'),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
        outstanding = Invoice.objects.filter(
            branch=self.branch, status=Invoice.Status.ISSUED
        ).aggregate(total=Sum(line_total))['total'] or Decimal('0.00')
        context = self.branch_context(
            active_customers=Customer.objects.filter(
                active=True, branch=self.branch
            ).count(),
            uninvoiced_count=WorkEntry.objects.filter(
                invoice_line__isnull=True,
                property__customer__branch=self.branch,
            ).count(),
            draft_count=Invoice.objects.filter(
                branch=self.branch, status=Invoice.Status.DRAFT
            ).count(),
            outstanding=outstanding,
            recent_invoices=Invoice.objects.filter(branch=self.branch)
            .select_related('customer')[:8],
            recent_work=WorkEntry.objects.filter(
                property__customer__branch=self.branch
            ).select_related(
                'property', 'property__customer'
            )[:8],
        )
        return render(request, self.template_name, context)


class CustomerListView(BranchContextMixin, OfficeAccessMixin, ListView):
    model = Customer
    template_name = 'office/customer_list.html'
    context_object_name = 'customers'

    def get_queryset(self):
        queryset = Customer.objects.filter(branch=self.branch).annotate(
            property_count=Count('properties', distinct=True),
            invoice_count=Count('invoices', distinct=True),
        )
        query = self.request.GET.get('q', '').strip()
        if query:
            queryset = queryset.filter(
                Q(display_name__icontains=query)
                | Q(contact_name__icontains=query)
                | Q(postcode__icontains=query)
                | Q(email__icontains=query)
            )
        return queryset


class CustomerCreateView(BranchContextMixin, OfficeAccessMixin, CreateView):
    model = Customer
    form_class = CustomerForm
    template_name = 'office/form.html'

    def form_valid(self, form):
        form.instance.branch = self.branch
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(page_title='New customer', submit_label='Save customer')
        return context

    def get_success_url(self):
        messages.success(self.request, 'Customer saved.')
        return self.branch_reverse('customer-detail', pk=self.object.pk)


class CustomerUpdateView(BranchContextMixin, OfficeAccessMixin, UpdateView):
    model = Customer
    form_class = CustomerForm
    template_name = 'office/form.html'

    def get_queryset(self):
        return Customer.objects.filter(branch=self.branch)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(page_title='Edit customer', submit_label='Save changes')
        return context

    def get_success_url(self):
        messages.success(self.request, 'Customer updated.')
        return self.branch_reverse('customer-detail', pk=self.object.pk)


class CustomerDetailView(BranchContextMixin, OfficeAccessMixin, DetailView):
    model = Customer
    template_name = 'office/customer_detail.html'
    context_object_name = 'customer'

    def get_queryset(self):
        return Customer.objects.filter(branch=self.branch).prefetch_related(
            'properties', 'invoices', 'properties__work_entries'
        )


class PropertyCreateView(BranchContextMixin, OfficeAccessMixin, CreateView):
    model = Property
    form_class = PropertyForm
    template_name = 'office/form.html'

    def dispatch(self, request, *args, **kwargs):
        self.branch = kwargs.get('branch')
        if self.branch not in BusinessBranch.values:
            raise PermissionDenied
        self.branch_meta = BRANCH_META[self.branch]
        self.customer = get_object_or_404(
            Customer, pk=kwargs['customer_pk'], branch=self.branch
        )
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.customer = self.customer
        return super().form_valid(form)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['customer'] = self.customer
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            page_title=f'New property for {self.customer.display_name}',
            submit_label='Save property',
        )
        return context

    def get_success_url(self):
        messages.success(self.request, 'Property saved.')
        return self.branch_reverse('customer-detail', pk=self.customer.pk)


class PropertyUpdateView(BranchContextMixin, OfficeAccessMixin, UpdateView):
    model = Property
    form_class = PropertyForm
    template_name = 'office/form.html'

    def get_queryset(self):
        return Property.objects.filter(customer__branch=self.branch)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['customer'] = self.object.customer
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(page_title='Edit property', submit_label='Save changes')
        return context

    def get_success_url(self):
        messages.success(self.request, 'Property updated.')
        return self.branch_reverse(
            'customer-detail', pk=self.object.customer_id
        )


class PropertyDeleteView(BranchContextMixin, OwnerOnlyMixin, View):
    def post(self, request, branch, pk):
        property_record = get_object_or_404(
            Property, pk=pk, customer__branch=self.branch
        )
        customer_id = property_record.customer_id
        try:
            property_record.delete()
        except ProtectedError:
            messages.error(
                request,
                'This property cannot be deleted because it has work or invoice history. '
                'Edit it and untick Active instead.',
            )
        else:
            messages.success(request, 'Property deleted.')
        return redirect(
            'office:customer-detail', branch=self.branch, pk=customer_id
        )


class WorkEntryListView(BranchContextMixin, OfficeAccessMixin, ListView):
    model = WorkEntry
    template_name = 'office/work_list.html'
    context_object_name = 'work_entries'
    paginate_by = 40

    def get_queryset(self):
        queryset = WorkEntry.objects.filter(
            property__customer__branch=self.branch
        ).select_related(
            'property', 'property__customer'
        )
        status = self.request.GET.get('status')
        if status == 'uninvoiced':
            queryset = queryset.filter(invoice_line__isnull=True)
        elif status == 'invoiced':
            queryset = queryset.filter(invoice_line__isnull=False)
        return queryset


class WorkEntryCreateView(BranchContextMixin, OfficeAccessMixin, CreateView):
    model = WorkEntry
    form_class = WorkEntryForm
    template_name = 'office/form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['branch'] = self.branch
        return kwargs

    def get_success_url(self):
        return self.branch_reverse('work-list')

    def get_initial(self):
        initial = super().get_initial()
        if self.request.GET.get('property'):
            initial['property'] = self.request.GET['property']
        return initial

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, 'Work entry saved.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(page_title='Record completed work', submit_label='Save work')
        return context


class WorkEntryUpdateView(BranchContextMixin, OfficeAccessMixin, UpdateView):
    model = WorkEntry
    form_class = WorkEntryForm
    template_name = 'office/form.html'

    def get_queryset(self):
        return WorkEntry.objects.filter(
            property__customer__branch=self.branch
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['branch'] = self.branch
        return kwargs

    def get_success_url(self):
        return self.branch_reverse('work-list')

    def dispatch(self, request, *args, **kwargs):
        self.branch = kwargs.get('branch')
        if self.branch not in BusinessBranch.values:
            raise PermissionDenied
        self.branch_meta = BRANCH_META[self.branch]
        entry = get_object_or_404(
            WorkEntry,
            pk=kwargs['pk'],
            property__customer__branch=self.branch,
        )
        if entry.is_invoiced:
            messages.error(request, 'Invoiced work entries cannot be changed.')
            return redirect('office:work-list', branch=self.branch)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(page_title='Edit work entry', submit_label='Save changes')
        return context


class InvoiceListView(BranchContextMixin, OfficeAccessMixin, ListView):
    model = Invoice
    template_name = 'office/invoice_list.html'
    context_object_name = 'invoices'
    paginate_by = 40

    def get_queryset(self):
        queryset = Invoice.objects.filter(branch=self.branch).select_related('customer', 'property').prefetch_related(
            'lines'
        )
        status = self.request.GET.get('status')
        if status in Invoice.Status.values:
            queryset = queryset.filter(status=status)
        return queryset


class InvoiceDetailView(BranchContextMixin, OfficeAccessMixin, DetailView):
    model = Invoice
    template_name = 'office/invoice_detail.html'
    context_object_name = 'invoice'

    def get_queryset(self):
        return Invoice.objects.filter(branch=self.branch).select_related('customer', 'property').prefetch_related(
            'lines', 'email_history__sent_by'
        )


class InvoiceCreateView(BranchContextMixin, OfficeAccessMixin, CreateView):
    model = Invoice
    form_class = InvoiceCreateForm
    template_name = 'office/form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['branch'] = self.branch
        return kwargs

    def form_valid(self, form):
        form.instance.branch = self.branch
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        append_work_entries(self.object, form.cleaned_data['work_entries'])
        messages.success(self.request, 'Draft invoice created. Check it before issuing.')
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            page_title='New invoice',
            submit_label='Create draft',
            invoice_form=True,
        )
        return context

    def get_success_url(self):
        return self.branch_reverse('invoice-edit', pk=self.object.pk)


class InvoiceEditView(BranchContextMixin, OfficeAccessMixin, View):
    template_name = 'office/invoice_edit.html'

    def get_invoice(self, pk):
        invoice = get_object_or_404(Invoice, pk=pk, branch=self.branch)
        if invoice.status != Invoice.Status.DRAFT:
            messages.warning(self.request, 'Issued invoices are locked.')
            return None
        return invoice

    def get(self, request, branch, pk):
        invoice = self.get_invoice(pk)
        if invoice is None:
            return redirect(
                'office:invoice-detail', branch=self.branch, pk=pk
            )
        return render(
            request,
            self.template_name,
            {
                'invoice': invoice,
                'form': InvoiceForm(instance=invoice, branch=self.branch),
                'formset': InvoiceLineFormSet(instance=invoice),
                'branch': self.branch,
                'branch_meta': self.branch_meta,
            },
        )

    def post(self, request, branch, pk):
        invoice = self.get_invoice(pk)
        if invoice is None:
            return redirect(
                'office:invoice-detail', branch=self.branch, pk=pk
            )
        form = InvoiceForm(request.POST, instance=invoice, branch=self.branch)
        formset = InvoiceLineFormSet(request.POST, instance=invoice)
        if form.is_valid() and formset.is_valid():
            selected_ids = list(
                form.cleaned_data['work_entries'].values_list('pk', flat=True)
            )
            with transaction.atomic():
                selected_work = list(
                    available_work_entries_for_update(selected_ids)
                )
                if len(selected_work) != len(selected_ids):
                    form.add_error(
                        'work_entries',
                        'One of these work entries has just been invoiced elsewhere. '
                        'Reload the draft and try again.',
                    )
                else:
                    form.save()
                    formset.save()
                    append_work_entries(invoice, selected_work)
            if form.errors:
                return render(
                    request,
                    self.template_name,
                    self.branch_context(
                        invoice=invoice, form=form, formset=formset
                    ),
                )
            messages.success(request, 'Draft invoice updated.')
            return redirect(
                'office:invoice-detail', branch=self.branch, pk=invoice.pk
            )
        return render(
            request,
            self.template_name,
            self.branch_context(invoice=invoice, form=form, formset=formset),
        )


class InvoiceIssueView(BranchContextMixin, OfficeAccessMixin, View):
    def post(self, request, branch, pk):
        invoice = get_object_or_404(Invoice, pk=pk, branch=self.branch)
        try:
            invoice = invoice.issue()
        except ValidationError as error:
            messages.error(request, '; '.join(error.messages))
            return redirect(
                'office:invoice-edit', branch=self.branch, pk=invoice.pk
            )
        messages.success(
            request,
            f'{invoice.number} has been issued and locked. The PDF is ready.',
        )
        return redirect(
            'office:invoice-detail', branch=self.branch, pk=invoice.pk
        )


class InvoicePdfView(BranchContextMixin, OfficeAccessMixin, View):
    def get(self, request, branch, pk):
        invoice = get_object_or_404(
            Invoice.objects.prefetch_related('lines'),
            pk=pk,
            branch=self.branch,
        )
        if invoice.status == Invoice.Status.DRAFT:
            messages.warning(request, 'Issue the invoice before downloading its PDF.')
            return redirect(
                'office:invoice-edit', branch=self.branch, pk=invoice.pk
            )
        content = build_invoice_pdf(invoice)
        response = HttpResponse(content, content_type='application/pdf')
        response['Content-Disposition'] = (
            f'attachment; filename="{invoice.number}.pdf"'
        )
        return response


class InvoiceEmailView(BranchContextMixin, OfficeAccessMixin, View):
    template_name = 'office/invoice_email.html'

    def get_invoice(self, pk):
        return get_object_or_404(
            Invoice.objects.select_related('customer').prefetch_related('lines'),
            pk=pk,
            branch=self.branch,
        )

    def initial(self, invoice):
        details = invoice.billing_details
        recipient_name = (
            details.get('contact_name') or details.get('display_name') or ''
        ).strip()
        greeting_name = (
            recipient_name.split(maxsplit=1)[0] if recipient_name else 'there'
        )
        return {
            'recipient': details.get('email', ''),
            'subject': f'Invoice {invoice.number} from Avonmoor Ltd',
            'message': (
                f'Dear {greeting_name},\n\n'
                f'Please find attached invoice {invoice.number}.\n\n'
                'Avonmoor Ltd'
            ),
        }

    def emailable_invoice(self, request, pk):
        invoice = self.get_invoice(pk)
        if invoice.status not in (Invoice.Status.ISSUED, Invoice.Status.PAID):
            messages.warning(request, 'Only issued or paid invoices can be emailed.')
            return invoice, redirect(
                'office:invoice-detail', branch=self.branch, pk=invoice.pk
            )
        return invoice, None

    def get(self, request, branch, pk):
        self.invoice, blocked = self.emailable_invoice(request, pk)
        if blocked:
            return blocked
        form = InvoiceEmailForm(initial=self.initial(self.invoice))
        return render(
            request,
            self.template_name,
            self.branch_context(invoice=self.invoice, form=form),
        )

    def post(self, request, branch, pk):
        self.invoice, blocked = self.emailable_invoice(request, pk)
        if blocked:
            return blocked
        form = InvoiceEmailForm(request.POST)
        if form.is_valid():
            email = EmailMessage(
                subject=form.cleaned_data['subject'],
                body=form.cleaned_data['message'],
                from_email=settings.EMAIL_HOST_USER,
                to=[form.cleaned_data['recipient']],
                reply_to=[settings.EMAIL_HOST_USER],
            )
            email.attach(
                f'{self.invoice.number}.pdf',
                build_invoice_pdf(self.invoice),
                'application/pdf',
            )
            try:
                email.send(fail_silently=False)
            except Exception:
                logger.exception('Invoice email could not be sent')
                messages.error(
                    request,
                    'The invoice email could not be sent. Check the address and try again.',
                )
            else:
                InvoiceEmail.objects.create(
                    invoice=self.invoice,
                    recipient=form.cleaned_data['recipient'],
                    subject=form.cleaned_data['subject'],
                    body=form.cleaned_data['message'],
                    sent_by=request.user,
                )
                messages.success(
                    request,
                    f'{self.invoice.number} emailed to {form.cleaned_data["recipient"]}.',
                )
                return redirect(
                    'office:invoice-detail',
                    branch=self.branch,
                    pk=self.invoice.pk,
                )
        return render(
            request,
            self.template_name,
            self.branch_context(invoice=self.invoice, form=form),
        )


class InvoiceMarkPaidView(BranchContextMixin, OfficeAccessMixin, View):
    def post(self, request, branch, pk):
        invoice = get_object_or_404(Invoice, pk=pk, branch=self.branch)
        try:
            invoice.mark_paid()
        except ValidationError as error:
            messages.error(request, '; '.join(error.messages))
        else:
            messages.success(request, f'{invoice.number} marked as paid.')
        return redirect(
            'office:invoice-detail', branch=self.branch, pk=invoice.pk
        )


class InvoiceCancelView(BranchContextMixin, OfficeAccessMixin, View):
    def post(self, request, branch, pk):
        invoice = get_object_or_404(Invoice, pk=pk, branch=self.branch)
        try:
            invoice.cancel()
        except ValidationError as error:
            messages.error(request, '; '.join(error.messages))
        else:
            messages.success(request, f'{invoice.number} cancelled.')
        return redirect(
            'office:invoice-detail', branch=self.branch, pk=invoice.pk
        )


class CustomerExportView(BranchContextMixin, OfficeAccessMixin, View):
    def get(self, request, branch):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = (
            f'attachment; filename="avonmoor-{self.branch}-customers.csv"'
        )
        writer = csv.writer(response)
        writer.writerow(
            [
                'Customer',
                'Contact',
                'Email',
                'Phone',
                'Billing address 1',
                'Billing address 2',
                'Town',
                'County',
                'Postcode',
                'Active',
            ]
        )
        for customer in Customer.objects.filter(branch=self.branch):
            writer.writerow(
                [
                    customer.display_name,
                    customer.contact_name,
                    customer.email,
                    customer.phone,
                    customer.billing_address_1,
                    customer.billing_address_2,
                    customer.town,
                    customer.county,
                    customer.postcode,
                    'Yes' if customer.active else 'No',
                ]
            )
        return response


class InvoiceExportView(BranchContextMixin, OfficeAccessMixin, View):
    def get(self, request, branch):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = (
            f'attachment; filename="avonmoor-{self.branch}-invoices.csv"'
        )
        writer = csv.writer(response)
        writer.writerow(
            [
                'Invoice number',
                'Issue date',
                'Customer',
                'Property',
                'Status',
                'Total',
                'Issued at',
                'Paid at',
                'Cancelled at',
            ]
        )
        invoices = Invoice.objects.filter(branch=self.branch).select_related(
            'customer', 'property'
        ).prefetch_related('lines')
        for invoice in invoices:
            writer.writerow(
                [
                    invoice.display_number,
                    invoice.issue_date.isoformat(),
                    invoice.billing_details.get('display_name', ''),
                    str(invoice.property) if invoice.property_id else '',
                    invoice.get_status_display(),
                    f'{invoice.total:.2f}',
                    invoice.issued_at.isoformat() if invoice.issued_at else '',
                    invoice.paid_at.isoformat() if invoice.paid_at else '',
                    invoice.cancelled_at.isoformat() if invoice.cancelled_at else '',
                ]
            )
        return response
