from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from .forms import RoofSectionForm, SurveyForm, SurveyUpdateForm
from .models import RoofSection, Survey
from .services.rainfall import apply_nearest_rainfall_to_survey


class OwnedSurveyMixin(LoginRequiredMixin):
    def get_queryset(self):
        queryset = Survey.objects.prefetch_related(
            Prefetch('roof_sections', queryset=RoofSection.objects.all())
        )
        if self.request.user.is_superuser:
            return queryset
        return queryset.filter(created_by=self.request.user)


class SurveyListView(OwnedSurveyMixin, ListView):
    model = Survey
    template_name = 'water_survey/survey_list.html'
    context_object_name = 'surveys'


class SurveyCreateView(LoginRequiredMixin, CreateView):
    model = Survey
    form_class = SurveyForm
    template_name = 'water_survey/survey_form.html'

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('water_survey:survey-detail', args=[self.object.pk])


class SurveyDetailView(OwnedSurveyMixin, DetailView):
    model = Survey
    template_name = 'water_survey/survey_detail.html'
    context_object_name = 'survey'


class SurveyReportView(OwnedSurveyMixin, DetailView):
    model = Survey
    template_name = 'water_survey/survey_report.html'
    context_object_name = 'survey'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['report_generated_at'] = timezone.localtime()
        return context


class SurveyUpdateView(OwnedSurveyMixin, UpdateView):
    model = Survey
    form_class = SurveyUpdateForm
    template_name = 'water_survey/survey_form.html'

    def form_valid(self, form):
        messages.success(self.request, 'Survey details have been updated.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('water_survey:survey-detail', args=[self.object.pk])


class SurveyDeleteView(OwnedSurveyMixin, DeleteView):
    model = Survey
    template_name = 'water_survey/survey_confirm_delete.html'
    success_url = reverse_lazy('water_survey:survey-list')

    def form_valid(self, form):
        survey_label = str(self.object)
        response = super().form_valid(form)
        messages.success(self.request, f'Survey “{survey_label}” was deleted.')
        return response


class OwnedRoofSectionMixin(LoginRequiredMixin):
    def get_queryset(self):
        queryset = RoofSection.objects.select_related('survey')
        if 'survey_pk' in self.kwargs:
            queryset = queryset.filter(survey_id=self.kwargs['survey_pk'])
        if self.request.user.is_superuser:
            return queryset
        return queryset.filter(survey__created_by=self.request.user)


class RoofSectionFormContextMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['survey'] = self.survey
        context['google_maps_api_key'] = settings.GOOGLE_MAPS_API_KEY
        context['map_address'] = ', '.join(
            part
            for part in (
                self.survey.property_name,
                self.survey.address_line_1,
                self.survey.town,
                self.survey.postcode,
                'UK',
            )
            if part
        )
        return context

    def save_map_location(self, form):
        latitude = form.cleaned_data.get('map_latitude')
        longitude = form.cleaned_data.get('map_longitude')
        if latitude is not None and longitude is not None:
            self.survey.latitude = latitude
            self.survey.longitude = longitude
            self.survey.save(update_fields=['latitude', 'longitude', 'updated_at'])
            apply_nearest_rainfall_to_survey(self.survey)

    def get_success_url(self):
        return reverse('water_survey:survey-detail', args=[self.survey.pk])


class RoofSectionCreateView(
    RoofSectionFormContextMixin, LoginRequiredMixin, CreateView
):
    model = RoofSection
    form_class = RoofSectionForm
    template_name = 'water_survey/roof_section_form.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        queryset = Survey.objects.all()
        if not request.user.is_superuser:
            queryset = queryset.filter(created_by=request.user)
        self.survey = get_object_or_404(queryset, pk=kwargs['survey_pk'])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.survey = self.survey
        self.save_map_location(form)
        return super().form_valid(form)


class RoofSectionUpdateView(
    RoofSectionFormContextMixin, OwnedRoofSectionMixin, UpdateView
):
    model = RoofSection
    form_class = RoofSectionForm
    template_name = 'water_survey/roof_section_form.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        self.object = self.get_object()
        self.survey = self.object.survey
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        initial.update(
            map_latitude=self.survey.latitude,
            map_longitude=self.survey.longitude,
        )
        return initial

    def form_valid(self, form):
        self.save_map_location(form)
        messages.success(self.request, 'Roof section has been updated.')
        return super().form_valid(form)


class RoofSectionDeleteView(OwnedRoofSectionMixin, DeleteView):
    model = RoofSection
    template_name = 'water_survey/roof_section_confirm_delete.html'

    def get_success_url(self):
        return reverse(
            'water_survey:survey-detail', args=[self.object.survey_id]
        )

    def form_valid(self, form):
        roof_name = self.object.name
        response = super().form_valid(form)
        messages.success(self.request, f'Roof section “{roof_name}” was deleted.')
        return response


class RainfallRefreshView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        queryset = Survey.objects.all()
        if not request.user.is_superuser:
            queryset = queryset.filter(created_by=request.user)
        survey = get_object_or_404(queryset, pk=kwargs['pk'])

        if survey.latitude is None or survey.longitude is None:
            messages.warning(
                request,
                'Measure a roof on the map first so the property has a location.',
            )
        elif apply_nearest_rainfall_to_survey(survey) is None:
            messages.warning(
                request,
                'No imported rainfall grid point was found near this property. '
                'The manual annual rainfall value is unchanged.',
            )
        else:
            messages.success(request, 'Local monthly rainfall has been updated.')

        return redirect('water_survey:survey-detail', pk=survey.pk)
