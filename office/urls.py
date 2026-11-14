from django.urls import path, register_converter

from . import banking_views, views, mileage_views

app_name = 'office'


class BranchConverter:
    regex = 'garden|rainwater'

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value


register_converter(BranchConverter, 'branch')

urlpatterns = [
    path('<branch:branch>/mileage/daily/', mileage_views.MileageEntryView.as_view(), {'daily': True}, name='mileage-daily'),
    path('<branch:branch>/mileage/', mileage_views.MileageListView.as_view(), name='mileage-list'),
    path('<branch:branch>/mileage/new/', mileage_views.MileageEntryView.as_view(), name='mileage-create'),
    path('<branch:branch>/mileage/<int:pk>/edit/', mileage_views.MileageEntryView.as_view(), name='mileage-edit'),
    path('<branch:branch>/mileage/<int:pk>/<str:action>/', mileage_views.MileageReviewView.as_view(), name='mileage-review'),
    path('<branch:branch>/mileage/claims/generate/', mileage_views.MileageGenerateView.as_view(), name='mileage-generate'),
    path('<branch:branch>/mileage/claims/<int:pk>/', mileage_views.MileageClaimView.as_view(), name='mileage-claim'),
    path('<branch:branch>/exports/mileage.csv', mileage_views.MileageExportView.as_view(), name='mileage-export'),
    path('', views.OfficeDashboardView.as_view(), name='dashboard'),
    path('accounting/', views.AccountingReportView.as_view(), name='accounting'),
    path('employees/', views.EmployeeListView.as_view(), name='employee-list'),
    path('employees/new/', views.EmployeeCreateView.as_view(), name='employee-create'),
    path('employees/<int:pk>/edit/', views.EmployeeUpdateView.as_view(), name='employee-edit'),
    path('payments/', banking_views.PaymentsView.as_view(), name='payments'),
    path(
        'expenses/inbox/',
        banking_views.ExpenseInboxView.as_view(),
        name='expense-inbox',
    ),
    path(
        'expenses/inbox/<int:pk>/review/',
        banking_views.BankExpenseReviewView.as_view(),
        name='expense-bank-review',
    ),
    path(
        'expenses/inbox/<int:pk>/exclude/',
        banking_views.BankExpenseIgnoreView.as_view(),
        name='expense-bank-ignore',
    ),
    path(
        'expenses/inbox/<int:pk>/restore/',
        banking_views.BankExpenseRestoreView.as_view(),
        name='expense-bank-restore',
    ),
    path(
        'payments/import/',
        banking_views.BankCSVImportView.as_view(),
        name='payment-import',
    ),
    path(
        'payments/<int:pk>/match/',
        banking_views.PaymentMatchView.as_view(),
        name='payment-match',
    ),
    path(
        'payments/<int:pk>/ignore/',
        banking_views.PaymentIgnoreView.as_view(),
        name='payment-ignore',
    ),
    path(
        'payments/<int:pk>/restore/',
        banking_views.PaymentRestoreView.as_view(),
        name='payment-restore',
    ),
    path(
        'payments/matches/<int:pk>/undo/',
        banking_views.PaymentUnmatchView.as_view(),
        name='payment-unmatch',
    ),
    path(
        'payments/monzo/connect/',
        banking_views.MonzoConnectView.as_view(),
        name='monzo-connect',
    ),
    path(
        'payments/monzo/callback/',
        banking_views.MonzoCallbackView.as_view(),
        name='monzo-callback',
    ),
    path(
        'payments/monzo/account/',
        banking_views.MonzoAccountView.as_view(),
        name='monzo-account',
    ),
    path(
        'payments/monzo/sync/',
        banking_views.MonzoSyncView.as_view(),
        name='monzo-sync',
    ),
    path(
        'payments/monzo/disconnect/',
        banking_views.MonzoDisconnectView.as_view(),
        name='monzo-disconnect',
    ),
    path(
        'payments/monzo/webhook/',
        banking_views.MonzoWebhookView.as_view(),
        name='monzo-webhook',
    ),
    path('<branch:branch>/', views.BranchDashboardView.as_view(), name='branch-dashboard'),
    path('<branch:branch>/customers/', views.CustomerListView.as_view(), name='customer-list'),
    path('<branch:branch>/customers/new/', views.CustomerCreateView.as_view(), name='customer-create'),
    path(
        '<branch:branch>/customers/<int:pk>/',
        views.CustomerDetailView.as_view(),
        name='customer-detail',
    ),
    path(
        '<branch:branch>/customers/<int:pk>/edit/',
        views.CustomerUpdateView.as_view(),
        name='customer-edit',
    ),
    path(
        '<branch:branch>/customers/<int:customer_pk>/properties/new/',
        views.PropertyCreateView.as_view(),
        name='property-create',
    ),
    path(
        '<branch:branch>/properties/<int:pk>/edit/',
        views.PropertyUpdateView.as_view(),
        name='property-edit',
    ),
    path(
        '<branch:branch>/properties/<int:pk>/delete/',
        views.PropertyDeleteView.as_view(),
        name='property-delete',
    ),
    path('<branch:branch>/work/', views.WorkEntryListView.as_view(), name='work-list'),
    path('<branch:branch>/work/new/', views.WorkEntryCreateView.as_view(), name='work-create'),
    path(
        '<branch:branch>/work/<int:pk>/edit/',
        views.WorkEntryUpdateView.as_view(),
        name='work-edit',
    ),
    path('<branch:branch>/expenses/', views.ExpenseListView.as_view(), name='expense-list'),
    path('<branch:branch>/expenses/new/', views.ExpenseCreateView.as_view(), name='expense-create'),
    path(
        '<branch:branch>/expenses/<int:pk>/edit/',
        views.ExpenseUpdateView.as_view(),
        name='expense-edit',
    ),
    path(
        '<branch:branch>/expenses/<int:pk>/void/',
        views.ExpenseVoidView.as_view(),
        name='expense-void',
    ),
    path('<branch:branch>/invoices/', views.InvoiceListView.as_view(), name='invoice-list'),
    path(
        '<branch:branch>/exports/customers.csv',
        views.CustomerExportView.as_view(),
        name='customer-export',
    ),
    path(
        '<branch:branch>/exports/invoices.csv',
        views.InvoiceExportView.as_view(),
        name='invoice-export',
    ),
    path(
        '<branch:branch>/exports/expenses.csv',
        views.ExpenseExportView.as_view(),
        name='expense-export',
    ),
    path('<branch:branch>/invoices/new/', views.InvoiceCreateView.as_view(), name='invoice-create'),
    path(
        '<branch:branch>/invoices/<int:pk>/',
        views.InvoiceDetailView.as_view(),
        name='invoice-detail',
    ),
    path(
        '<branch:branch>/invoices/<int:pk>/edit/',
        views.InvoiceEditView.as_view(),
        name='invoice-edit',
    ),
    path(
        '<branch:branch>/invoices/<int:pk>/delete/',
        views.InvoiceDeleteView.as_view(),
        name='invoice-delete',
    ),
    path(
        '<branch:branch>/invoices/<int:pk>/issue/',
        views.InvoiceIssueView.as_view(),
        name='invoice-issue',
    ),
    path(
        '<branch:branch>/invoices/<int:pk>/pdf/',
        views.InvoicePdfView.as_view(),
        name='invoice-pdf',
    ),
    path(
        '<branch:branch>/invoices/<int:pk>/email/',
        views.InvoiceEmailView.as_view(),
        name='invoice-email',
    ),
    path(
        '<branch:branch>/invoices/<int:pk>/paid/',
        views.InvoiceMarkPaidView.as_view(),
        name='invoice-paid',
    ),
    path(
        '<branch:branch>/invoices/<int:pk>/cancel/',
        views.InvoiceCancelView.as_view(),
        name='invoice-cancel',
    ),
    # Garden compatibility routes preserve existing bookmarks and integrations.
    path('customers/', views.CustomerListView.as_view(), {'branch': 'garden'}, name='customer-list'),
    path('customers/new/', views.CustomerCreateView.as_view(), {'branch': 'garden'}, name='customer-create'),
    path('customers/<int:pk>/', views.CustomerDetailView.as_view(), {'branch': 'garden'}, name='customer-detail'),
    path('customers/<int:pk>/edit/', views.CustomerUpdateView.as_view(), {'branch': 'garden'}, name='customer-edit'),
    path('customers/<int:customer_pk>/properties/new/', views.PropertyCreateView.as_view(), {'branch': 'garden'}, name='property-create'),
    path('properties/<int:pk>/edit/', views.PropertyUpdateView.as_view(), {'branch': 'garden'}, name='property-edit'),
    path('properties/<int:pk>/delete/', views.PropertyDeleteView.as_view(), {'branch': 'garden'}, name='property-delete'),
    path('work/', views.WorkEntryListView.as_view(), {'branch': 'garden'}, name='work-list'),
    path('work/new/', views.WorkEntryCreateView.as_view(), {'branch': 'garden'}, name='work-create'),
    path('work/<int:pk>/edit/', views.WorkEntryUpdateView.as_view(), {'branch': 'garden'}, name='work-edit'),
    path('invoices/', views.InvoiceListView.as_view(), {'branch': 'garden'}, name='invoice-list'),
    path('exports/customers.csv', views.CustomerExportView.as_view(), {'branch': 'garden'}, name='customer-export'),
    path('exports/invoices.csv', views.InvoiceExportView.as_view(), {'branch': 'garden'}, name='invoice-export'),
    path('invoices/new/', views.InvoiceCreateView.as_view(), {'branch': 'garden'}, name='invoice-create'),
    path('invoices/<int:pk>/', views.InvoiceDetailView.as_view(), {'branch': 'garden'}, name='invoice-detail'),
    path('invoices/<int:pk>/edit/', views.InvoiceEditView.as_view(), {'branch': 'garden'}, name='invoice-edit'),
    path('invoices/<int:pk>/delete/', views.InvoiceDeleteView.as_view(), {'branch': 'garden'}, name='invoice-delete'),
    path('invoices/<int:pk>/issue/', views.InvoiceIssueView.as_view(), {'branch': 'garden'}, name='invoice-issue'),
    path('invoices/<int:pk>/pdf/', views.InvoicePdfView.as_view(), {'branch': 'garden'}, name='invoice-pdf'),
    path('invoices/<int:pk>/email/', views.InvoiceEmailView.as_view(), {'branch': 'garden'}, name='invoice-email'),
    path('invoices/<int:pk>/paid/', views.InvoiceMarkPaidView.as_view(), {'branch': 'garden'}, name='invoice-paid'),
    path('invoices/<int:pk>/cancel/', views.InvoiceCancelView.as_view(), {'branch': 'garden'}, name='invoice-cancel'),
]
