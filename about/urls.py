from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),  # The landing page (root of the about section)
]