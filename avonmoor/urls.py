"""
URL configuration for avonmoor project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from contact import views as contact_views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', contact_views.home_view, name='home'),
    path(
        'garden-property-maintenance/',
        contact_views.garden_property_view,
        name='garden_property',
    ),
    path(
        'rainwater-harvesting/',
        contact_views.rainwater_harvesting_view,
        name='rainwater_harvesting',
    ),
    path('contact/', contact_views.contact_view, name='contact'),
    path('privacy/', contact_views.privacy_view, name='privacy'),
    path('accounts/', include('django.contrib.auth.urls')),
    path('rainwater-calculator/', include('water_calculator.urls')),
    path('surveys/', include('water_survey.urls')),
    path('admin/', admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
