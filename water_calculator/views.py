from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View

from .forms import PropertyForm, RoofEstimateForm, SurveyRequestForm
from .services import RainfallUnavailable, build_public_estimate


PROPERTY_SESSION_KEY = 'water_calculator_property'
ESTIMATE_SESSION_KEY = 'water_calculator_estimate'
REPORT_UNLOCKED_SESSION_KEY = 'water_calculator_report_unlocked'


class PropertyStepView(View):
    template_name = 'water_calculator/property_step.html'

    def get(self, request):
        form = PropertyForm(initial=request.session.get(PROPERTY_SESSION_KEY))
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = PropertyForm(request.POST)
        if form.is_valid():
            request.session.set_expiry(3600)
            request.session[PROPERTY_SESSION_KEY] = form.cleaned_data
            request.session.pop(ESTIMATE_SESSION_KEY, None)
            request.session.pop(REPORT_UNLOCKED_SESSION_KEY, None)
            return redirect('water_calculator:measure')
        return render(request, self.template_name, {'form': form})


class RoofMeasureStepView(View):
    template_name = 'water_calculator/roof_step.html'

    def dispatch(self, request, *args, **kwargs):
        self.property_data = request.session.get(PROPERTY_SESSION_KEY)
        if not self.property_data:
            return redirect('water_calculator:start')
        return super().dispatch(request, *args, **kwargs)

    def get_context(self, form):
        address = ', '.join(
            part
            for part in (
                self.property_data.get('address_line_1'),
                self.property_data.get('town'),
                self.property_data.get('postcode'),
                'UK',
            )
            if part
        )
        return {
            'form': form,
            'property': self.property_data,
            'map_address': address,
            'google_maps_api_key': settings.GOOGLE_MAPS_API_KEY,
        }

    def get(self, request):
        return render(
            request,
            self.template_name,
            self.get_context(RoofEstimateForm()),
        )

    def post(self, request):
        form = RoofEstimateForm(request.POST)
        if form.is_valid():
            try:
                estimate = build_public_estimate(
                    self.property_data, form.cleaned_data
                )
            except RainfallUnavailable as error:
                form.add_error(None, str(error))
            else:
                request.session[ESTIMATE_SESSION_KEY] = estimate
                request.session.pop(REPORT_UNLOCKED_SESSION_KEY, None)
                return redirect('water_calculator:results')
        return render(request, self.template_name, self.get_context(form))


class ResultsView(View):
    template_name = 'water_calculator/results.html'

    def get(self, request):
        estimate = request.session.get(ESTIMATE_SESSION_KEY)
        if not estimate:
            return redirect('water_calculator:start')
        return render(
            request,
            self.template_name,
            {
                'estimate': estimate,
                'lead_form': SurveyRequestForm(),
                'full_report_unlocked': request.session.get(
                    REPORT_UNLOCKED_SESSION_KEY, False
                ),
            },
        )


class SurveyRequestView(View):
    def post(self, request):
        estimate = request.session.get(ESTIMATE_SESSION_KEY)
        if not estimate:
            return redirect('water_calculator:start')

        form = SurveyRequestForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                'water_calculator/results.html',
                {
                    'estimate': estimate,
                    'lead_form': form,
                    'full_report_unlocked': False,
                },
            )

        lead = form.save(commit=False)
        lead.address_line_1 = estimate['address_line_1']
        lead.town = estimate['town']
        lead.postcode = estimate['postcode']
        lead.latitude = Decimal(estimate['latitude'])
        lead.longitude = Decimal(estimate['longitude'])
        lead.roof_area_m2 = Decimal(estimate['roof_area_m2'])
        lead.roof_polygon = estimate['roof_polygon']
        lead.roof_material = estimate['roof_material']
        lead.intended_use = estimate['intended_use']
        lead.has_existing_collection = estimate['has_existing_collection']
        lead.annual_rainfall_mm = Decimal(estimate['annual_rainfall_mm'])
        lead.estimated_annual_harvest_litres = Decimal(
            estimate['annual_harvest_litres']
        )
        lead.indicative_storage_low_litres = estimate['storage_low_litres']
        lead.indicative_storage_high_litres = estimate['storage_high_litres']
        lead.rainfall_source = estimate['rainfall_source']
        lead.rainfall_reference_period = estimate['rainfall_reference_period']
        lead.consented_at = timezone.now()
        lead.save()

        subject = f'Full rainwater estimate accessed - {lead.postcode}'
        body = (
            f'New calculator estimate access\n\n'
            f'Name: {lead.name}\nEmail: {lead.email}\nPhone: {lead.phone}\n'
            f'Address: {lead.address_line_1}, {lead.town}, {lead.postcode}\n'
            f'Roof area: {lead.roof_area_m2} m2\n'
            f'Estimated harvest: {lead.estimated_annual_harvest_litres} L/year\n'
            f'Reference: {lead.reference}\n'
        )
        send_mail(
            subject,
            body,
            settings.EMAIL_HOST_USER,
            [settings.EMAIL_HOST_USER],
            fail_silently=True,
        )
        request.session[REPORT_UNLOCKED_SESSION_KEY] = True
        messages.success(request, 'Your full rainwater estimate is now available.')
        return redirect(reverse('water_calculator:results'))


class ThanksView(View):
    template_name = 'water_calculator/thanks.html'

    def get(self, request):
        reference = request.session.pop(
            'water_calculator_lead_reference', None
        )
        if not reference:
            messages.info(request, 'Start a new estimate when you are ready.')
            return redirect('water_calculator:start')
        return render(request, self.template_name, {'reference': reference})
