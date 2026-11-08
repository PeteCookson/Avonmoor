import csv
import logging
from datetime import date
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
    ExpenseForm,
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
    Expense,
    Invoice,
    InvoiceEmail,
    InvoiceLine,
    Property,
    WorkEntry,
    MileageClaim,
)
from .mailbox import append_message_to_sent
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


def _money_total(records, attribute='total'):
    return sum(
        (getattr(record, attribute) for record in records), Decimal('0.00')
    ).quantize(Decimal('0.01'))


def _month_sequence(start_date, end_date):
    current = start_date.replace(day=1)
    final = end_date.replace(day=1)
    while current <= final:
        yield current
        current = (
            date(current.year + 1, 1, 1)
            if current.month == 12
            else date(current.year, current.month + 1, 1)
        )


def build_accounting_report(start_date, end_date, branch='all'):
    """Build an operational cash and invoice summary for Office."""

    branch_filter = {} if branch == 'all' else {'branch': branch}
    sales_invoices = list(
        Invoice.objects.filter(
            **branch_filter,
            issue_date__range=(start_date, end_date),
            status__in=(Invoice.Status.ISSUED, Invoice.Status.PAID),
        )
        .select_related('customer')
        .prefetch_related('lines')
    )
    paid_invoices = list(
        Invoice.objects.filter(
            **branch_filter,
            paid_at__date__range=(start_date, end_date),
            status=Invoice.Status.PAID,
        )
        .select_related('customer')
        .prefetch_related('lines')
    )
    expenses = list(
        Expense.objects.filter(
            **branch_filter,
            expense_date__range=(start_date, end_date),
            voided_at__isnull=True,
        ).select_related('property', 'property__customer')
    )
    outstanding_invoices = list(
        Invoice.objects.filter(
            **branch_filter, status=Invoice.Status.ISSUED
        )
        .select_related('customer')
        .prefetch_related('lines')
    )

    invoiced_sales = _money_total(sales_invoices)
    recorded_payments = _money_total(paid_invoices)
    expense_total = _money_total(expenses, 'amount')
    mileage_claims = list(MileageClaim.objects.filter(**branch_filter, status__in=['approved', 'paid']))
    cash_expenses = [expense for expense in expenses if expense.category != Expense.Category.MILEAGE]
    paid_mileage = [claim for claim in mileage_claims if claim.status == 'paid' and start_date <= timezone.localdate(claim.paid_at) <= end_date]
    cash_expense_total = _money_total(cash_expenses, 'amount') + _money_total(paid_mileage)
    mileage_owed = _money_total((claim for claim in mileage_claims if claim.status == 'approved'))
    current_outstanding = _money_total(outstanding_invoices)

    months = []
    for month in _month_sequence(start_date, end_date):
        monthly_sales = _money_total(
            invoice
            for invoice in sales_invoices
            if invoice.issue_date.year == month.year
            and invoice.issue_date.month == month.month
        )
        monthly_payments = _money_total(
            invoice
            for invoice in paid_invoices
            if invoice.paid_at.date().year == month.year
            and invoice.paid_at.date().month == month.month
        )
        monthly_expenses = _money_total(
            (
                expense
                for expense in expenses
                if expense.expense_date.year == month.year
                and expense.expense_date.month == month.month
            ),
            'amount',
        )
        monthly_cash_expenses = _money_total((expense for expense in cash_expenses if expense.expense_date.year == month.year and expense.expense_date.month == month.month), 'amount') + _money_total((claim for claim in paid_mileage if timezone.localdate(claim.paid_at).replace(day=1) == month))
        months.append(
            {
                'month': month,
                'sales': monthly_sales,
                'payments': monthly_payments,
                'expenses': monthly_expenses,
                'position': monthly_payments - monthly_cash_expenses,
            }
        )

    branch_rows = []
    if branch == 'all':
        for value, label in BusinessBranch.choices:
            branch_sales = _money_total(
                invoice for invoice in sales_invoices if invoice.branch == value
            )
            branch_payments = _money_total(
                invoice for invoice in paid_invoices if invoice.branch == value
            )
            branch_expenses = _money_total(
                (expense for expense in expenses if expense.branch == value),
                'amount',
            )
            branch_rows.append(
                {
                    'value': value,
                    'label': label,
                    'sales': branch_sales,
                    'payments': branch_payments,
                    'expenses': branch_expenses,
                    'position': branch_payments - _money_total((expense for expense in cash_expenses if expense.branch == value), 'amount') - _money_total((claim for claim in paid_mileage if claim.branch == value)),
                }
            )

    today = timezone.localdate()
    aged_invoices = []
    age_buckets = {
        '0–30 days': Decimal('0.00'),
        '31–60 days': Decimal('0.00'),
        '61–90 days': Decimal('0.00'),
        'Over 90 days': Decimal('0.00'),
    }
    for invoice in sorted(outstanding_invoices, key=lambda item: item.issue_date):
        age_days = max((today - invoice.issue_date).days, 0)
        if age_days <= 30:
            bucket = '0–30 days'
        elif age_days <= 60:
            bucket = '31–60 days'
        elif age_days <= 90:
            bucket = '61–90 days'
        else:
            bucket = 'Over 90 days'
        age_buckets[bucket] += invoice.total
        aged_invoices.append(
            {'invoice': invoice, 'age_days': age_days, 'bucket': bucket}
        )

    return {
        'invoiced_sales': invoiced_sales,
        'recorded_payments': recorded_payments,
        'expense_total': expense_total,
        'cash_position': recorded_payments - cash_expense_total,
        'cash_expense_total': cash_expense_total,
        'mileage_owed': mileage_owed,
        'mileage_expense_total': _money_total((expense for expense in expenses if expense.category == Expense.Category.MILEAGE), 'amount'),
        'current_outstanding': current_outstanding,
        'months': months,
        'branch_rows': branch_rows,
        'aged_invoices': aged_invoices,
        'age_buckets': [
            {'label': label, 'amount': amount}
            for label, amount in age_buckets.items()
        ],
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


class AccountingReportView(OfficeAccessMixin, View):
    template_name = 'office/accounting.html'

    def report_parameters(self, request):
        today = timezone.localdate()
        default_start = date(today.year, 1, 1)
        error = ''
        try:
            start_date = date.fromisoformat(
                request.GET.get('start', default_start.isoformat())
            )
            end_date = date.fromisoformat(
                request.GET.get('end', today.isoformat())
            )
        except ValueError:
            start_date, end_date = default_start, today
            error = 'Enter valid report dates.'
        if start_date > end_date:
            start_date, end_date = default_start, today
            error = 'The report start date must be before the end date.'
        if (end_date - start_date).days > 1827:
            start_date, end_date = default_start, today
            error = 'Choose a report period of five years or less.'

        branch = request.GET.get('branch', 'all')
        if branch not in ('all', *BusinessBranch.values):
            branch = 'all'
            error = 'Choose a valid business branch.'
        return start_date, end_date, branch, error

    def csv_response(self, report, start_date, end_date, branch):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = (
            'attachment; filename='
            f'"avonmoor-accounting-{branch}-{start_date}-{end_date}.csv"'
        )
        writer = csv.writer(response)
        writer.writerow(['Avonmoor accounting summary'])
        writer.writerow(['Period', start_date.isoformat(), end_date.isoformat()])
        writer.writerow(['Branch', branch])
        writer.writerow([])
        writer.writerow(['Metric', 'Amount'])
        writer.writerow(['Invoiced sales', f'{report["invoiced_sales"]:.2f}'])
        writer.writerow(['Recorded payments', f'{report["recorded_payments"]:.2f}'])
        writer.writerow(['Recorded expenses', f'{report["expense_total"]:.2f}'])
        writer.writerow(['Mileage expenses (approved)', f'{report["mileage_expense_total"]:.2f}'])
        writer.writerow(['Mileage awaiting payment (all dates)', f'{report["mileage_owed"]:.2f}'])
        writer.writerow(['Paid expenses in period', f'{report["cash_expense_total"]:.2f}'])
        writer.writerow(['Recorded cash position', f'{report["cash_position"]:.2f}'])
        writer.writerow(['Current outstanding', f'{report["current_outstanding"]:.2f}'])
        writer.writerow([])
        writer.writerow(
            ['Month', 'Invoiced sales', 'Recorded payments', 'Expenses', 'Cash position']
        )
        for row in report['months']:
            writer.writerow(
                [
                    row['month'].strftime('%Y-%m'),
                    f'{row["sales"]:.2f}',
                    f'{row["payments"]:.2f}',
                    f'{row["expenses"]:.2f}',
                    f'{row["position"]:.2f}',
                ]
            )
        if report['branch_rows']:
            writer.writerow([])
            writer.writerow(
                ['Branch', 'Invoiced sales', 'Recorded payments', 'Expenses', 'Cash position']
            )
            for row in report['branch_rows']:
                writer.writerow(
                    [
                        row['label'],
                        f'{row["sales"]:.2f}',
                        f'{row["payments"]:.2f}',
                        f'{row["expenses"]:.2f}',
                        f'{row["position"]:.2f}',
                    ]
                )
        writer.writerow([])
        writer.writerow(
            ['Outstanding invoice', 'Branch', 'Customer', 'Issue date', 'Age days', 'Amount']
        )
        for row in report['aged_invoices']:
            invoice = row['invoice']
            writer.writerow(
                [
                    invoice.display_number,
                    invoice.get_branch_display(),
                    invoice.customer.display_name,
                    invoice.issue_date.isoformat(),
                    row['age_days'],
                    f'{invoice.total:.2f}',
                ]
            )
        return response

    def get(self, request):
        start_date, end_date, branch, error = self.report_parameters(request)
        report = build_accounting_report(start_date, end_date, branch)
        if request.GET.get('export') == 'csv':
            return self.csv_response(report, start_date, end_date, branch)
        return render(
            request,
            self.template_name,
            {
                **report,
                'start_date': start_date,
                'end_date': end_date,
                'selected_branch': branch,
                'branch_choices': [('all', 'All branches'), *BusinessBranch.choices],
                'report_error': error,
            },
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
            mileage_owed=MileageClaim.objects.filter(branch=self.branch, status='approved').aggregate(total=Sum('total'))['total'] or Decimal('0.00'),
            expense_total=Expense.objects.filter(
                branch=self.branch,
                voided_at__isnull=True,
                expense_date__year=timezone.localdate().year,
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00'),
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


class ExpenseListView(BranchContextMixin, OfficeAccessMixin, ListView):
    model = Expense
    template_name = 'office/expense_list.html'
    context_object_name = 'expenses'
    paginate_by = 40

    def get_queryset(self):
        queryset = Expense.objects.filter(branch=self.branch).select_related(
            'property', 'property__customer', 'created_by', 'voided_by'
        )
        status = self.request.GET.get('status', 'active')
        if status == 'void':
            queryset = queryset.filter(voided_at__isnull=False)
        elif status != 'all':
            queryset = queryset.filter(voided_at__isnull=True)
        category = self.request.GET.get('category', '')
        if category in Expense.Category.values:
            queryset = queryset.filter(category=category)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filtered = self.get_queryset()
        context.update(
            expense_total=filtered.aggregate(total=Sum('amount'))['total']
            or Decimal('0.00'),
            selected_status=self.request.GET.get('status', 'active'),
            selected_category=self.request.GET.get('category', ''),
            expense_categories=Expense.Category.choices,
        )
        return context


class ExpenseCreateView(BranchContextMixin, OfficeAccessMixin, CreateView):
    model = Expense
    form_class = ExpenseForm
    template_name = 'office/form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['branch'] = self.branch
        return kwargs

    def form_valid(self, form):
        form.instance.branch = self.branch
        form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        messages.success(self.request, 'Expense saved.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(page_title='Record expense', submit_label='Save expense')
        return context

    def get_success_url(self):
        return self.branch_reverse('expense-list')


class ExpenseUpdateView(BranchContextMixin, OfficeAccessMixin, UpdateView):
    model = Expense
    form_class = ExpenseForm
    template_name = 'office/form.html'

    def get_queryset(self):
        return Expense.objects.filter(branch=self.branch, voided_at__isnull=True, mileage_claim__isnull=True)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['branch'] = self.branch
        return kwargs

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, 'Expense updated.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(page_title='Edit expense', submit_label='Save changes')
        return context

    def get_success_url(self):
        return self.branch_reverse('expense-list')


class ExpenseVoidView(BranchContextMixin, OwnerOnlyMixin, View):
    def post(self, request, branch, pk):
        expense = get_object_or_404(
            Expense, pk=pk, branch=self.branch, voided_at__isnull=True, mileage_claim__isnull=True
        )
        try:
            expense.void(request.user)
        except ValidationError as error:
            messages.error(request, '; '.join(error.messages))
        else:
            messages.success(
                request,
                'Expense voided. It remains in the audit trail and CSV export.',
            )
        return redirect('office:expense-list', branch=self.branch)


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
            'lines',
            'email_history__sent_by',
            'payment_matches__transaction',
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
                try:
                    append_message_to_sent(email)
                except Exception:
                    logger.exception(
                        'Invoice email was sent but could not be copied to Sent'
                    )
                    messages.warning(
                        request,
                        f'{self.invoice.number} was emailed to '
                        f'{form.cleaned_data["recipient"]}, but the mailbox copy '
                        'could not be saved in Sent. The Office email history was saved.',
                    )
                else:
                    messages.success(
                        request,
                        f'{self.invoice.number} emailed to '
                        f'{form.cleaned_data["recipient"]} and saved in Sent.',
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


class ExpenseExportView(BranchContextMixin, OfficeAccessMixin, View):
    def get(self, request, branch):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = (
            f'attachment; filename="avonmoor-{self.branch}-expenses.csv"'
        )
        writer = csv.writer(response)
        writer.writerow(
            [
                'Date',
                'Supplier',
                'Category',
                'Description',
                'Customer',
                'Property',
                'Amount',
                'Payment method',
                'Reference',
                'Bank transaction ID',
                'Notes',
                'Status',
                'Created by',
                'Created at',
                'Voided by',
                'Voided at',
            ]
        )
        expenses = Expense.objects.filter(branch=self.branch).select_related(
            'property',
            'property__customer',
            'created_by',
            'voided_by',
            'bank_transaction',
        )
        for expense in expenses:
            writer.writerow(
                [
                    expense.expense_date.isoformat(),
                    expense.supplier,
                    expense.get_category_display(),
                    expense.description,
                    expense.property.customer.display_name
                    if expense.property_id
                    else '',
                    str(expense.property) if expense.property_id else '',
                    f'{expense.amount:.2f}',
                    expense.get_payment_method_display(),
                    expense.reference,
                    expense.bank_transaction.external_id
                    if expense.bank_transaction_id
                    else '',
                    expense.notes,
                    'Void' if expense.is_void else 'Active',
                    expense.created_by.get_username(),
                    expense.created_at.isoformat(),
                    expense.voided_by.get_username()
                    if expense.voided_by_id
                    else '',
                    expense.voided_at.isoformat() if expense.voided_at else '',
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
