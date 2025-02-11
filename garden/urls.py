from django.urls import path
from . import views

urlpatterns = [
    path('', views.garden, name='garden'),  # The landing page (root of the about section)
]