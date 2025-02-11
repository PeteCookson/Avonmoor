from django.urls import path
from . import views

urlpatterns = [
    path('', views.blog, name='blog'),  # The landing page (root of the about section)
]