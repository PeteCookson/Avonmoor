from django.urls import path

from .views import (
    RainfallRefreshView,
    RoofSectionCreateView,
    RoofSectionDeleteView,
    RoofSectionUpdateView,
    SurveyCreateView,
    SurveyDeleteView,
    SurveyDetailView,
    SurveyListView,
    SurveyReportView,
    SurveyUpdateView,
    SystemAssessmentView,
)

app_name = 'water_survey'

urlpatterns = [
    path('', SurveyListView.as_view(), name='survey-list'),
    path('new/', SurveyCreateView.as_view(), name='survey-create'),
    path('<int:pk>/', SurveyDetailView.as_view(), name='survey-detail'),
    path('<int:pk>/report/', SurveyReportView.as_view(), name='survey-report'),
    path(
        '<int:pk>/system-assessment/',
        SystemAssessmentView.as_view(),
        name='system-assessment',
    ),
    path('<int:pk>/edit/', SurveyUpdateView.as_view(), name='survey-update'),
    path('<int:pk>/delete/', SurveyDeleteView.as_view(), name='survey-delete'),
    path(
        '<int:pk>/rainfall/refresh/',
        RainfallRefreshView.as_view(),
        name='rainfall-refresh',
    ),
    path(
        '<int:survey_pk>/roof-sections/new/',
        RoofSectionCreateView.as_view(),
        name='roof-section-create',
    ),
    path(
        '<int:survey_pk>/roof-sections/<int:pk>/edit/',
        RoofSectionUpdateView.as_view(),
        name='roof-section-update',
    ),
    path(
        '<int:survey_pk>/roof-sections/<int:pk>/delete/',
        RoofSectionDeleteView.as_view(),
        name='roof-section-delete',
    ),
]
