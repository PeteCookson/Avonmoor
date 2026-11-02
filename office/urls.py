from django.urls import path

from . import views

app_name = 'office'

urlpatterns = [
    path('', views.OfficeDashboardView.as_view(), name='dashboard'),
    path('customers/', views.CustomerListView.as_view(), name='customer-list'),
    path('customers/new/', views.CustomerCreateView.as_view(), name='customer-create'),
    path(
        'customers/<int:pk>/',
        views.CustomerDetailView.as_view(),
        name='customer-detail',
    ),
    path(
        'customers/<int:pk>/edit/',
        views.CustomerUpdateView.as_view(),
        name='customer-edit',
    ),
    path(
        'customers/<int:customer_pk>/properties/new/',
        views.PropertyCreateView.as_view(),
        name='property-create',
    ),
    path(
        'properties/<int:pk>/edit/',
        views.PropertyUpdateView.as_view(),
        name='property-edit',
    ),
    path(
        'properties/<int:pk>/delete/',
        views.PropertyDeleteView.as_view(),
        name='property-delete',
    ),
    path('work/', views.WorkEntryListView.as_view(), name='work-list'),
    path('work/new/', views.WorkEntryCreateView.as_view(), name='work-create'),
    path(
        'work/<int:pk>/edit/',
        views.WorkEntryUpdateView.as_view(),
        name='work-edit',
    ),
    path('invoices/', views.InvoiceListView.as_view(), name='invoice-list'),
    path(
        'exports/customers.csv',
        views.CustomerExportView.as_view(),
        name='customer-export',
    ),
    path(
        'exports/invoices.csv',
        views.InvoiceExportView.as_view(),
        name='invoice-export',
    ),
    path('invoices/new/', views.InvoiceCreateView.as_view(), name='invoice-create'),
    path(
        'invoices/<int:pk>/',
        views.InvoiceDetailView.as_view(),
        name='invoice-detail',
    ),
    path(
        'invoices/<int:pk>/edit/',
        views.InvoiceEditView.as_view(),
        name='invoice-edit',
    ),
    path(
        'invoices/<int:pk>/issue/',
        views.InvoiceIssueView.as_view(),
        name='invoice-issue',
    ),
    path(
        'invoices/<int:pk>/pdf/',
        views.InvoicePdfView.as_view(),
        name='invoice-pdf',
    ),
    path(
        'invoices/<int:pk>/email/',
        views.InvoiceEmailView.as_view(),
        name='invoice-email',
    ),
    path(
        'invoices/<int:pk>/paid/',
        views.InvoiceMarkPaidView.as_view(),
        name='invoice-paid',
    ),
    path(
        'invoices/<int:pk>/cancel/',
        views.InvoiceCancelView.as_view(),
        name='invoice-cancel',
    ),
]
