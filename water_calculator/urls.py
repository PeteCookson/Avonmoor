from django.urls import path

from .views import (
    PropertyStepView,
    PostcodeLocationView,
    ResultsView,
    RoofMeasureStepView,
    SiteSurveyRequestView,
    SurveyRequestView,
    ThanksView,
)


app_name = 'water_calculator'

urlpatterns = [
    path('', PropertyStepView.as_view(), name='start'),
    path('measure-roof/', RoofMeasureStepView.as_view(), name='measure'),
    path(
        'postcode-location/',
        PostcodeLocationView.as_view(),
        name='postcode-location',
    ),
    path('results/', ResultsView.as_view(), name='results'),
    path('unlock-results/', SurveyRequestView.as_view(), name='unlock-results'),
    path(
        'request-site-survey/',
        SiteSurveyRequestView.as_view(),
        name='request-site-survey',
    ),
    path('thanks/', ThanksView.as_view(), name='thanks'),
]
