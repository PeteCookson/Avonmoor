from decimal import Decimal

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from water_survey.models import RainfallGridPoint

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
        self.assertContains(response, 'js/roof_measure.js')

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
        self.assertIsNotNone(lead.consented_at)
        self.assertEqual(len(mail.outbox), 1)

        unlocked_response = self.client.get(reverse('water_calculator:results'))
        self.assertContains(unlocked_response, 'Planning range, not a final specification')
        self.assertContains(unlocked_response, 'Met Office HadUK-Grid')
        self.assertContains(unlocked_response, 'Potential Currently Uncaptured')
        self.assertNotContains(unlocked_response, 'Unlock the Detailed Results')

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
