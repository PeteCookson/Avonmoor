from django.urls import path

from .views import (
    RoofSectionCreateView,
    SurveyCreateView,
    SurveyDetailView,
    SurveyListView,
)

app_name = 'water_survey'

urlpatterns = [
    path('', SurveyListView.as_view(), name='survey-list'),
    path('new/', SurveyCreateView.as_view(), name='survey-create'),
    path('<int:pk>/', SurveyDetailView.as_view(), name='survey-detail'),
    path(
        '<int:survey_pk>/roof-sections/new/',
        RoofSectionCreateView.as_view(),
        name='roof-section-create',
    ),
]
