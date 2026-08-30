import json
from collections import OrderedDict
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import override_settings
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .models import RainfallGridPoint, RoofSection, Survey
from .services.calculations import (
    calculate_monthly_yields,
    calculate_yield_litres,
)
from .services.geometry import calculate_geojson_area_m2
from .services.rainfall import (
    apply_nearest_rainfall_to_survey,
    find_nearest_rainfall_point,
)


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
TEST_MONTHLY_RAINFALL = {
    'jan': '100.00',
    'feb': '80.00',
    'mar': '75.00',
    'apr': '60.00',
    'may': '55.00',
    'jun': '50.00',
    'jul': '45.00',
    'aug': '55.00',
    'sep': '70.00',
    'oct': '90.00',
    'nov': '105.00',
    'dec': '115.00',
}


def create_rainfall_point(**overrides):
    values = {
        'grid_reference': 'test-grid-1',
        'latitude': Decimal('50.426100'),
        'longitude': Decimal('-3.834100'),
        'monthly_rainfall_mm': TEST_MONTHLY_RAINFALL,
        'annual_rainfall_mm': Decimal('900.00'),
        'source_name': 'Met Office HadUK-Grid',
        'source_version': 'v1.3.2.ceda',
        'reference_period': '1991-2020',
        'resolution_km': Decimal('1.00'),
    }
    values.update(overrides)
    return RainfallGridPoint.objects.create(**values)


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


class RainfallLookupTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='rainfall-surveyor', password='test-password'
        )
        self.survey = Survey.objects.create(
            created_by=self.user,
            address_line_1='1 Rain Lane',
            postcode='TQ10 9AB',
            latitude=Decimal('50.426000'),
            longitude=Decimal('-3.834000'),
            annual_rainfall_mm=Decimal('1100'),
        )
        self.roof = RoofSection.objects.create(
            survey=self.survey,
            area_m2=Decimal('10'),
            runoff_coefficient=Decimal('1'),
            system_efficiency=Decimal('1'),
        )

    def test_nearest_grid_point_is_selected(self):
        nearest = create_rainfall_point()
        create_rainfall_point(
            grid_reference='test-grid-2',
            latitude=Decimal('50.500000'),
            longitude=Decimal('-3.900000'),
        )

        result, distance = find_nearest_rainfall_point(
            self.survey.latitude, self.survey.longitude
        )

        self.assertEqual(result, nearest)
        self.assertLess(distance, Decimal('0.02'))

    def test_grid_values_are_copied_to_survey(self):
        point = create_rainfall_point()

        result = apply_nearest_rainfall_to_survey(self.survey)

        self.survey.refresh_from_db()
        self.assertEqual(result, point)
        self.assertEqual(self.survey.annual_rainfall_mm, Decimal('900.00'))
        self.assertEqual(self.survey.monthly_rainfall_mm['jan'], '100.00')
        self.assertEqual(self.survey.rainfall_reference_period, '1991-2020')
        self.assertEqual(
            self.survey.monthly_yield_rows[0]['yield_litres'],
            Decimal('1000.00'),
        )

    def test_no_grid_point_preserves_manual_fallback(self):
        result = apply_nearest_rainfall_to_survey(self.survey)

        self.survey.refresh_from_db()
        self.assertIsNone(result)
        self.assertEqual(self.survey.annual_rainfall_mm, Decimal('1100.00'))
        self.assertEqual(self.survey.monthly_rainfall_mm, {})

    def test_refresh_endpoint_applies_rainfall(self):
        create_rainfall_point()
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('water_survey:rainfall-refresh', args=[self.survey.pk]),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Local monthly rainfall has been updated.')
        self.assertContains(response, 'January')
        self.assertContains(response, '1,000 L')

    def test_other_user_cannot_refresh_survey(self):
        other_user = get_user_model().objects.create_user(
            username='rainfall-other', password='test-password'
        )
        self.client.force_login(other_user)

        response = self.client.post(
            reverse('water_survey:rainfall-refresh', args=[self.survey.pk])
        )

        self.assertEqual(response.status_code, 404)


class RainfallImportCommandTests(TestCase):
    def test_csv_import_creates_grid_point_and_calculates_annual_total(self):
        headers = [
            'grid_reference',
            'latitude',
            'longitude',
            *TEST_MONTHLY_RAINFALL,
            'source_name',
            'source_version',
            'reference_period',
            'resolution_km',
        ]
        row = [
            'sx-123-456',
            '50.4261',
            '-3.8341',
            *TEST_MONTHLY_RAINFALL.values(),
            'Met Office HadUK-Grid',
            'v1.3.2.ceda',
            '1991-2020',
            '1',
        ]
        with TemporaryDirectory() as directory:
            csv_path = Path(directory) / 'rainfall.csv'
            csv_path.write_text(
                ','.join(headers) + '\n' + ','.join(row) + '\n',
                encoding='utf-8',
            )
            call_command('import_rainfall_grid', csv_path)

        point = RainfallGridPoint.objects.get(grid_reference='sx-123-456')
        self.assertEqual(point.annual_rainfall_mm, Decimal('900.00'))
        self.assertEqual(point.monthly_rainfall_mm['dec'], '115.00')


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
        self.roof = RoofSection.objects.create(
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

    def test_owner_can_edit_survey_and_status(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('water_survey:survey-update', args=[self.survey.pk]),
            {
                'property_name': 'Test Cottage',
                'address_line_1': '2 Updated Lane',
                'town': 'South Brent',
                'postcode': 'TQ10 9AB',
                'annual_rainfall_mm': '1200',
                'status': Survey.Status.SURVEYED,
                'notes': 'Updated access note.',
            },
        )

        self.assertRedirects(
            response,
            reverse('water_survey:survey-detail', args=[self.survey.pk]),
        )
        self.survey.refresh_from_db()
        self.assertEqual(self.survey.property_name, 'Test Cottage')
        self.assertEqual(self.survey.status, Survey.Status.SURVEYED)
        self.assertEqual(self.survey.annual_rainfall_mm, Decimal('1200.00'))

    def test_grid_backed_survey_edit_hides_manual_rainfall(self):
        point = create_rainfall_point()
        self.survey.latitude = Decimal('50.426000')
        self.survey.longitude = Decimal('-3.834000')
        self.survey.save(update_fields=['latitude', 'longitude'])
        apply_nearest_rainfall_to_survey(self.survey)
        self.client.force_login(self.user)

        response = self.client.get(
            reverse('water_survey:survey-update', args=[self.survey.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="id_annual_rainfall_mm"')

        response = self.client.post(
            reverse('water_survey:survey-update', args=[self.survey.pk]),
            {
                'property_name': 'Grid Cottage',
                'address_line_1': self.survey.address_line_1,
                'town': '',
                'postcode': self.survey.postcode,
                'status': Survey.Status.SURVEYED,
                'notes': '',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.survey.refresh_from_db()
        self.assertEqual(self.survey.rainfall_grid_point, point)
        self.assertEqual(self.survey.annual_rainfall_mm, Decimal('900.00'))

    def test_other_user_cannot_edit_or_delete_survey(self):
        self.client.force_login(self.other_user)

        edit_response = self.client.get(
            reverse('water_survey:survey-update', args=[self.survey.pk])
        )
        delete_response = self.client.post(
            reverse('water_survey:survey-delete', args=[self.survey.pk])
        )

        self.assertEqual(edit_response.status_code, 404)
        self.assertEqual(delete_response.status_code, 404)
        self.assertTrue(Survey.objects.filter(pk=self.survey.pk).exists())

    def test_survey_delete_requires_confirmation_post(self):
        self.client.force_login(self.user)
        url = reverse('water_survey:survey-delete', args=[self.survey.pk])

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Delete this survey?')
        self.assertTrue(Survey.objects.filter(pk=self.survey.pk).exists())

        response = self.client.post(url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'was deleted')
        self.assertFalse(Survey.objects.filter(pk=self.survey.pk).exists())
        self.assertFalse(RoofSection.objects.filter(pk=self.roof.pk).exists())

    @override_settings(GOOGLE_MAPS_API_KEY='restricted-browser-key')
    def test_add_roof_page_includes_map_when_key_is_configured(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse('water_survey:roof-section-create', args=[self.survey.pk])
        )

        self.assertContains(response, 'id="roof-map"')
        self.assertContains(response, 'restricted-browser-key')

    @override_settings(GOOGLE_MAPS_API_KEY='restricted-browser-key')
    def test_edit_roof_page_restores_existing_polygon(self):
        self.roof.polygon = TEST_ROOF_POLYGON
        self.roof.save(update_fields=['polygon'])
        self.client.force_login(self.user)

        response = self.client.get(
            reverse(
                'water_survey:roof-section-update',
                args=[self.survey.pk, self.roof.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Edit roof section')
        self.assertEqual(response.context['form'].initial['polygon'], TEST_ROOF_POLYGON)

    def test_owner_can_edit_roof_and_area_is_recalculated(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse(
                'water_survey:roof-section-update',
                args=[self.survey.pk, self.roof.pk],
            ),
            {
                'name': 'Updated main roof',
                'downpipe_label': 'DP1',
                'roof_material': RoofSection.RoofMaterial.METAL,
                'area_m2': '999.00',
                'runoff_coefficient': '0.920',
                'system_efficiency': '0.950',
                'polygon': json.dumps(TEST_ROOF_POLYGON),
                'map_latitude': '50.426000',
                'map_longitude': '-3.834000',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.roof.refresh_from_db()
        self.assertEqual(self.roof.name, 'Updated main roof')
        self.assertEqual(self.roof.roof_material, RoofSection.RoofMaterial.METAL)
        self.assertGreater(self.roof.area_m2, Decimal('77'))
        self.assertLess(self.roof.area_m2, Decimal('81'))

    def test_other_user_cannot_edit_or_delete_roof(self):
        self.client.force_login(self.other_user)
        edit_url = reverse(
            'water_survey:roof-section-update',
            args=[self.survey.pk, self.roof.pk],
        )
        delete_url = reverse(
            'water_survey:roof-section-delete',
            args=[self.survey.pk, self.roof.pk],
        )

        self.assertEqual(self.client.get(edit_url).status_code, 404)
        self.assertEqual(self.client.post(delete_url).status_code, 404)
        self.assertTrue(RoofSection.objects.filter(pk=self.roof.pk).exists())

    def test_roof_delete_requires_confirmation_post(self):
        self.client.force_login(self.user)
        url = reverse(
            'water_survey:roof-section-delete',
            args=[self.survey.pk, self.roof.pk],
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Delete this roof section?')
        self.assertTrue(RoofSection.objects.filter(pk=self.roof.pk).exists())

        response = self.client.post(url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'was deleted')
        self.assertFalse(RoofSection.objects.filter(pk=self.roof.pk).exists())
        self.assertTrue(Survey.objects.filter(pk=self.survey.pk).exists())

    def test_polygon_area_is_recalculated_on_server(self):
        rainfall_point = create_rainfall_point()
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
        self.assertEqual(self.survey.rainfall_grid_point, rainfall_point)
        self.assertEqual(self.survey.annual_rainfall_mm, Decimal('900.00'))
