from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.generic import CreateView, DetailView, ListView

from .forms import RoofSectionForm, SurveyForm
from .models import RoofSection, Survey


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


class RoofSectionCreateView(LoginRequiredMixin, CreateView):
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
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['survey'] = self.survey
        return context

    def get_success_url(self):
        return reverse('water_survey:survey-detail', args=[self.survey.pk])
