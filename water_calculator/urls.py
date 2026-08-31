from django.urls import path

from .views import (
    PropertyStepView,
    ResultsView,
    RoofMeasureStepView,
    SurveyRequestView,
    ThanksView,
)


app_name = 'water_calculator'

urlpatterns = [
    path('', PropertyStepView.as_view(), name='start'),
    path('measure-roof/', RoofMeasureStepView.as_view(), name='measure'),
    path('results/', ResultsView.as_view(), name='results'),
    path('request-survey/', SurveyRequestView.as_view(), name='request-survey'),
    path('thanks/', ThanksView.as_view(), name='thanks'),
]
