import json
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from water_survey.models import RainfallGridPoint, RoofSection, Survey

from .models import CustomerSurveyLead
from .services import build_public_estimate


class PublicEstimateServiceTests(TestCase):
    def setUp(self):
        self.point = RainfallGridPoint.objects.create(
            grid_reference='public-test-point',
            latitude=Decimal('50.426000'),
            longitude=Decimal('-3.834000'),
            monthly_rainfall_mm={
                month: '100.00'
                for month in (
                    'jan', 'feb', 'mar', 'apr', 'may', 'jun',
                    'jul', 'aug', 'sep', 'oct', 'nov', 'dec',
                )
            },
            annual_rainfall_mm=Decimal('1200.00'),
            source_name='Met Office HadUK-Grid',
            source_version='v1.3.2.ceda',
            reference_period='1991-2020',
            resolution_km=Decimal('1.00'),
        )

    def test_builds_transparent_yield_and_storage_estimate(self):
        estimate = build_public_estimate(
            {
                'address_line_1': '1 Test Lane',
                'town': 'South Brent',
                'postcode': 'TQ10 9AB',
            },
            {
                'map_latitude': Decimal('50.426000'),
                'map_longitude': Decimal('-3.834000'),
                'area_m2': Decimal('80.00'),
                'roof_material': 'slate_tile',
                'intended_use': 'garden',
                'has_existing_collection': False,
            },
        )

        self.assertEqual(estimate['gross_rainfall_litres'], '96000.00')
        self.assertEqual(estimate['annual_harvest_litres'], '79800.00')
        self.assertEqual(estimate['uncaptured_litres'], '79800.00')
        self.assertEqual(estimate['storage_low_litres'], 3000)
        self.assertEqual(estimate['storage_high_litres'], 5000)
        self.assertEqual(len(estimate['monthly_rows']), 12)

    def test_existing_collection_avoids_claiming_all_yield_is_lost(self):
        estimate = build_public_estimate(
            {
                'address_line_1': '1 Test Lane',
                'town': '',
                'postcode': 'TQ10 9AB',
            },
            {
                'map_latitude': Decimal('50.426000'),
                'map_longitude': Decimal('-3.834000'),
                'area_m2': Decimal('80.00'),
                'roof_material': 'slate_tile',
                'intended_use': 'garden',
                'has_existing_collection': True,
            },
        )

        self.assertIsNone(estimate['uncaptured_litres'])

    def test_estimate_records_approximate_postcode_location_method(self):
        estimate = build_public_estimate(
            {
                'address_line_1': '1 Test Lane',
                'town': 'South Brent',
                'postcode': 'TQ10 9AB',
            },
            {
                'map_latitude': Decimal('50.426000'),
                'map_longitude': Decimal('-3.834000'),
                'location_method': 'postcode',
                'area_m2': Decimal('80.00'),
                'roof_material': 'slate_tile',
                'intended_use': 'garden',
                'has_existing_collection': False,
            },
        )

        self.assertEqual(estimate['location_method'], 'postcode')


class PublicCalculatorJourneyTests(TestCase):
    def setUp(self):
        RainfallGridPoint.objects.create(
            grid_reference='journey-test-point',
            latitude=Decimal('50.426000'),
            longitude=Decimal('-3.834000'),
            monthly_rainfall_mm={
                month: '100.00'
                for month in (
                    'jan', 'feb', 'mar', 'apr', 'may', 'jun',
                    'jul', 'aug', 'sep', 'oct', 'nov', 'dec',
                )
            },
            annual_rainfall_mm=Decimal('1200.00'),
            source_name='Met Office HadUK-Grid',
            source_version='v1.3.2.ceda',
            reference_period='1991-2020',
            resolution_km=Decimal('1.00'),
        )

    def _complete_estimate(self, location_method='map'):
        self.client.post(
            reverse('water_calculator:start'),
            {
                'address_line_1': '1 Test Lane',
                'town': 'South Brent',
                'postcode': 'tq10 9ab',
            },
        )
        return self.client.post(
            reverse('water_calculator:measure'),
            {
                'map_latitude': '50.426000',
                'map_longitude': '-3.834000',
                'location_method': location_method,
                'area_m2': '80.00',
                'roof_material': 'slate_tile',
                'intended_use': 'garden',
                'has_existing_collection': 'False',
                'polygon': '',
            },
        )

    def test_start_page_is_public_and_does_not_create_a_lead(self):
        response = self.client.get(reverse('water_calculator:start'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'How much rainwater is your roof losing?')
        self.assertContains(response, 'href="/" class="brand-logo"')
        self.assertContains(response, 'img/favicon.ico')
        self.assertContains(response, 'img/favicon-32x32.png')
        self.assertEqual(CustomerSurveyLead.objects.count(), 0)

    def test_property_step_redirects_to_map_measurement(self):
        response = self.client.post(
            reverse('water_calculator:start'),
            {
                'address_line_1': '1 Test Lane',
                'town': 'South Brent',
                'postcode': 'tq10 9ab',
            },
        )

        self.assertRedirects(response, reverse('water_calculator:measure'))
        self.assertEqual(
            self.client.session['water_calculator_property']['postcode'],
            'TQ10 9AB',
        )

    @override_settings(GOOGLE_MAPS_API_KEY='test-browser-key')
    def test_measure_page_uses_public_location_aware_roof_map(self):
        self.client.post(
            reverse('water_calculator:start'),
            {
                'address_line_1': '1 Test Lane',
                'town': 'South Brent',
                'postcode': 'TQ10 9AB',
            },
        )

        response = self.client.get(reverse('water_calculator:measure'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-requires-location="true"')
        self.assertContains(response, 'data-postcode="TQ10 9AB"')
        self.assertContains(response, 'Use the Postcode Fallback')
        self.assertContains(response, 'data-lookup-url="/rainwater-calculator/postcode-location/"')
        self.assertContains(
            response,
            'This measures the flat ground area covered by the roof',
        )
        self.assertContains(response, 'js/roof_measure.js')

    @patch('water_calculator.views.urlopen')
    def test_postcode_location_uses_same_origin_server_lookup(self, mock_urlopen):
        self.client.post(
            reverse('water_calculator:start'),
            {
                'address_line_1': '1 Test Lane',
                'town': 'South Brent',
                'postcode': 'TQ10 9AB',
            },
        )
        api_response = mock_urlopen.return_value.__enter__.return_value
        api_response.read.return_value = json.dumps({
            'status': 200,
            'result': {'latitude': 50.426723, 'longitude': -3.835181},
        }).encode('utf-8')

        response = self.client.get(
            reverse('water_calculator:postcode-location'),
            {'postcode': 'TQ109AB'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            'latitude': 50.426723,
            'longitude': -3.835181,
        })
        mock_urlopen.assert_called_once()

    @patch('water_calculator.views.urlopen')
    def test_postcode_location_rejects_postcode_outside_session(
        self, mock_urlopen
    ):
        self.client.post(
            reverse('water_calculator:start'),
            {
                'address_line_1': '1 Test Lane',
                'town': 'South Brent',
                'postcode': 'TQ10 9AB',
            },
        )

        response = self.client.get(
            reverse('water_calculator:postcode-location'),
            {'postcode': 'PL1 1AA'},
        )

        self.assertEqual(response.status_code, 400)
        mock_urlopen.assert_not_called()

    @override_settings(GOOGLE_MAPS_API_KEY='')
    def test_measure_page_can_continue_when_google_maps_is_unavailable(self):
        self.client.post(
            reverse('water_calculator:start'),
            {
                'address_line_1': '1 Test Lane',
                'town': 'South Brent',
                'postcode': 'TQ10 9AB',
            },
        )

        response = self.client.get(reverse('water_calculator:measure'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'You can still calculate')
        self.assertContains(response, 'Use Postcode Location')
        self.assertContains(response, 'Calculate My Rainwater Potential')
        self.assertContains(response, 'js/roof_measure.js')

    def test_measurement_creates_session_result_not_database_lead(self):
        response = self._complete_estimate()

        self.assertRedirects(response, reverse('water_calculator:results'))
        self.assertEqual(CustomerSurveyLead.objects.count(), 0)
        estimate = self.client.session['water_calculator_estimate']
        self.assertEqual(estimate['annual_harvest_litres'], '79800.00')

    def test_public_results_show_value_without_revealing_full_report(self):
        self._complete_estimate()

        response = self.client.get(reverse('water_calculator:results'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '79,800')
        self.assertContains(response, 'class="result-unit">litres/year</span>')
        self.assertContains(response, 'Unlock the Detailed Results')
        self.assertNotContains(response, 'Planning range, not a final specification')
        self.assertNotContains(response, 'Met Office HadUK-Grid')

    def test_postcode_fallback_result_discloses_approximate_location(self):
        self._complete_estimate(location_method='postcode')

        response = self.client.get(reverse('water_calculator:results'))

        self.assertContains(response, 'an approximate postcode-centre location')

    def test_results_require_a_completed_estimate(self):
        response = self.client.get(reverse('water_calculator:results'))

        self.assertRedirects(response, reverse('water_calculator:start'))

    def test_contact_details_unlock_full_report_and_create_lead(self):
        self._complete_estimate()

        response = self.client.post(
            reverse('water_calculator:unlock-results'),
            {
                'name': 'Alex Customer',
                'email': 'alex@example.com',
                'phone': '',
                'website': '',
                'consent': 'on',
            },
        )

        lead = CustomerSurveyLead.objects.get()
        self.assertRedirects(response, reverse('water_calculator:results'))
        self.assertEqual(lead.postcode, 'TQ10 9AB')
        self.assertEqual(lead.roof_area_m2, Decimal('80.00'))
        self.assertEqual(
            lead.estimated_annual_harvest_litres, Decimal('79800.00')
        )
        self.assertEqual(lead.gross_rainfall_litres, Decimal('96000.00'))
        self.assertEqual(lead.runoff_coefficient, Decimal('0.875'))
        self.assertEqual(lead.system_efficiency, Decimal('0.950'))
        self.assertEqual(lead.location_method, 'map')
        self.assertEqual(lead.rainfall_distance_km, Decimal('0.00'))
        self.assertEqual(len(lead.monthly_estimate), 12)
        self.assertIsNotNone(lead.consented_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('RAINWATER LEAD', mail.outbox[0].subject)
        self.assertEqual(mail.outbox[0].reply_to, ['alex@example.com'])
        self.assertIn('#30569A', mail.outbox[0].alternatives[0][0])
        self.assertIn('Detailed Estimate Accessed', mail.outbox[0].body)

        unlocked_response = self.client.get(reverse('water_calculator:results'))
        self.assertContains(unlocked_response, 'Planning range, not a final specification')
        self.assertContains(unlocked_response, 'Met Office HadUK-Grid')
        self.assertContains(unlocked_response, 'Potential Currently Uncaptured')
        self.assertNotContains(unlocked_response, 'Unlock the Detailed Results')

    def test_repeated_unlock_submission_does_not_duplicate_lead(self):
        self._complete_estimate()
        data = {
            'name': 'Alex Customer',
            'email': 'alex@example.com',
            'phone': '',
            'website': '',
            'consent': 'on',
        }

        self.client.post(reverse('water_calculator:unlock-results'), data)
        response = self.client.post(
            reverse('water_calculator:unlock-results'), data
        )

        self.assertRedirects(response, reverse('water_calculator:results'))
        self.assertEqual(CustomerSurveyLead.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_customer_can_request_site_survey_without_second_contact_form(self):
        self._complete_estimate()
        self.client.post(
            reverse('water_calculator:unlock-results'),
            {
                'name': 'Alex Customer',
                'email': 'alex@example.com',
                'phone': '',
                'website': '',
                'consent': 'on',
            },
        )

        response = self.client.post(
            reverse('water_calculator:request-site-survey')
        )

        lead = CustomerSurveyLead.objects.get()
        self.assertRedirects(response, reverse('water_calculator:results'))
        self.assertEqual(
            lead.status, CustomerSurveyLead.Status.SURVEY_REQUESTED
        )
        self.assertIsNotNone(lead.survey_requested_at)
        self.assertEqual(len(mail.outbox), 2)
        survey_email = mail.outbox[1]
        self.assertIn('RAINWATER SURVEY REQUESTED', survey_email.subject)
        self.assertIn('Site Survey Requested', survey_email.body)
        self.assertIn('79,800 litres/year', survey_email.body)

        result = self.client.get(reverse('water_calculator:results'))
        self.assertContains(result, 'Survey Request Received')
        self.assertContains(result, 'you will not need to enter them again')
        self.assertNotContains(result, 'Request a Site Survey')

        self.client.post(reverse('water_calculator:request-site-survey'))
        self.assertEqual(len(mail.outbox), 2)

    def test_admin_can_create_survey_from_calculator_lead(self):
        self._complete_estimate()
        self.client.post(
            reverse('water_calculator:unlock-results'),
            {
                'name': 'Alex Customer',
                'email': 'alex@example.com',
                'phone': '07123 456 789',
                'website': '',
                'consent': 'on',
            },
        )
        lead = CustomerSurveyLead.objects.get()
        user = get_user_model().objects.create_superuser(
            username='lead-admin',
            email='admin@example.com',
            password='test-password',
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse('admin:water_calculator_customersurveylead_changelist'),
            {
                'action': 'create_survey_records',
                '_selected_action': [str(lead.pk)],
            },
        )

        self.assertEqual(response.status_code, 302)
        lead.refresh_from_db()
        self.assertIsNotNone(lead.survey_id)
        survey = Survey.objects.get(pk=lead.survey_id)
        self.assertEqual(survey.created_by, user)
        self.assertEqual(survey.postcode, 'TQ10 9AB')
        self.assertEqual(survey.monthly_rainfall_mm['jan'], '100.00')
        roof = RoofSection.objects.get(survey=survey)
        self.assertEqual(roof.area_m2, Decimal('80.00'))
        self.assertEqual(roof.roof_material, 'slate_tile')
        self.assertEqual(roof.runoff_coefficient, Decimal('0.875'))

        detail = self.client.get(
            reverse('water_survey:survey-detail', args=[survey.pk])
        )
        self.assertContains(detail, 'Customer and Calculator Lead')
        self.assertContains(detail, 'Alex Customer')
        self.assertContains(detail, 'alex@example.com')
        self.assertContains(detail, 'Calculator Leads')

    def test_honeypot_rejects_automated_submission(self):
        self._complete_estimate()

        response = self.client.post(
            reverse('water_calculator:unlock-results'),
            {
                'name': 'Spam Bot',
                'email': 'spam@example.com',
                'website': 'https://spam.example',
                'consent': 'on',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Unable to submit this request.')
        self.assertEqual(CustomerSurveyLead.objects.count(), 0)
