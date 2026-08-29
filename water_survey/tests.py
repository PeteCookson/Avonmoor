import json
from collections import OrderedDict
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .models import RoofSection, Survey
from .services.calculations import (
    calculate_monthly_yields,
    calculate_yield_litres,
)
from .services.geometry import calculate_geojson_area_m2


TEST_ROOF_POLYGON = {
    'type': 'Polygon',
    'coordinates': [[
        [-3.8340, 50.4260],
        [-3.8339, 50.4260],
        [-3.8339, 50.4261],
        [-3.8340, 50.4261],
        [-3.8340, 50.4260],
    ]],
}


class YieldCalculationTests(SimpleTestCase):
    def test_example_annual_yield(self):
        result = calculate_yield_litres(
            area_m2=80,
            rainfall_mm=1100,
            runoff_coefficient=0.9,
            system_efficiency=0.95,
        )

        self.assertEqual(result, Decimal('75240.00'))

    def test_zero_rainfall_returns_zero(self):
        result = calculate_yield_litres(area_m2=80, rainfall_mm=0)

        self.assertEqual(result, Decimal('0.00'))

    def test_invalid_coefficient_is_rejected(self):
        with self.assertRaisesMessage(ValueError, 'between 0 and 1'):
            calculate_yield_litres(
                area_m2=80,
                rainfall_mm=1100,
                runoff_coefficient=1.1,
            )

    def test_monthly_yields_preserve_month_order(self):
        rainfall = OrderedDict([('Jan', 100), ('Feb', 50)])

        result = calculate_monthly_yields(
            area_m2=10,
            monthly_rainfall_mm=rainfall,
            runoff_coefficient=1,
            system_efficiency=1,
        )

        self.assertEqual(list(result), ['Jan', 'Feb'])
        self.assertEqual(result['Jan'], Decimal('1000.00'))


class GeometryCalculationTests(SimpleTestCase):
    def test_geojson_polygon_returns_horizontal_area(self):
        area = calculate_geojson_area_m2(TEST_ROOF_POLYGON)

        self.assertGreater(area, Decimal('77'))
        self.assertLess(area, Decimal('81'))

    def test_polygon_requires_three_different_points(self):
        polygon = {
            'type': 'Polygon',
            'coordinates': [[[-3.8, 50.4], [-3.7, 50.5], [-3.8, 50.4]]],
        }

        with self.assertRaisesMessage(ValueError, 'three different points'):
            calculate_geojson_area_m2(polygon)


class SurveyAccessTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='surveyor', password='test-password'
        )
        self.other_user = get_user_model().objects.create_user(
            username='other', password='test-password'
        )
        self.survey = Survey.objects.create(
            created_by=self.user,
            address_line_1='1 Test Lane',
            postcode='TQ10 9AB',
            annual_rainfall_mm=Decimal('1100'),
        )
        RoofSection.objects.create(
            survey=self.survey,
            area_m2=Decimal('80'),
            runoff_coefficient=Decimal('0.9'),
            system_efficiency=Decimal('0.95'),
        )

    def test_survey_list_requires_login(self):
        response = self.client.get(reverse('water_survey:survey-list'))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('water_survey:survey-list')}",
        )

    def test_add_roof_requires_login(self):
        url = reverse(
            'water_survey:roof-section-create', args=[self.survey.pk]
        )

        response = self.client.get(url)

        self.assertRedirects(response, f"{reverse('login')}?next={url}")

    def test_owner_can_view_survey_and_yield(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse('water_survey:survey-detail', args=[self.survey.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '75,240')

    def test_other_user_cannot_view_survey(self):
        self.client.force_login(self.other_user)

        response = self.client.get(
            reverse('water_survey:survey-detail', args=[self.survey.pk])
        )

        self.assertEqual(response.status_code, 404)

    @override_settings(GOOGLE_MAPS_API_KEY='restricted-browser-key')
    def test_add_roof_page_includes_map_when_key_is_configured(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse('water_survey:roof-section-create', args=[self.survey.pk])
        )

        self.assertContains(response, 'id="roof-map"')
        self.assertContains(response, 'restricted-browser-key')

    def test_polygon_area_is_recalculated_on_server(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('water_survey:roof-section-create', args=[self.survey.pk]),
            {
                'name': 'Garage roof',
                'downpipe_label': 'DP2',
                'roof_material': RoofSection.RoofMaterial.SLATE_TILE,
                'area_m2': '999.00',
                'runoff_coefficient': '0.850',
                'system_efficiency': '0.950',
                'polygon': json.dumps(TEST_ROOF_POLYGON),
                'map_latitude': '50.426000',
                'map_longitude': '-3.834000',
            },
        )

        self.assertEqual(response.status_code, 302)
        roof = RoofSection.objects.get(name='Garage roof')
        self.assertNotEqual(roof.area_m2, Decimal('999.00'))
        self.assertGreater(roof.area_m2, Decimal('77'))
        self.assertLess(roof.area_m2, Decimal('81'))
        self.survey.refresh_from_db()
        self.assertEqual(self.survey.latitude, Decimal('50.426000'))
        self.assertEqual(self.survey.longitude, Decimal('-3.834000'))
