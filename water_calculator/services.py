from decimal import Decimal, ROUND_HALF_UP

from water_survey.models import RoofSection
from water_survey.services.calculations import calculate_yield_litres
from water_survey.services.rainfall import (
    MONTHS,
    find_nearest_rainfall_point,
    normalise_monthly_rainfall,
)

from .constants import INTENDED_USE_CHOICES


SYSTEM_EFFICIENCY = Decimal('0.95')
RUNOFF_COEFFICIENTS = {
    RoofSection.RoofMaterial.METAL: Decimal('0.925'),
    RoofSection.RoofMaterial.SLATE_TILE: Decimal('0.875'),
    RoofSection.RoofMaterial.ROUGH_TILE: Decimal('0.825'),
    RoofSection.RoofMaterial.GREEN: Decimal('0.450'),
    RoofSection.RoofMaterial.OTHER: Decimal('0.800'),
}
STANDARD_STORAGE_LITRES = (1000, 1500, 2500, 3000, 5000, 7500, 10000)


class RainfallUnavailable(ValueError):
    pass


def _storage_range(annual_harvest_litres):
    target = Decimal(annual_harvest_litres) * Decimal('0.05')
    if target <= STANDARD_STORAGE_LITRES[0]:
        return STANDARD_STORAGE_LITRES[0], STANDARD_STORAGE_LITRES[1]
    if target >= STANDARD_STORAGE_LITRES[-1]:
        return STANDARD_STORAGE_LITRES[-1], None

    lower = max(size for size in STANDARD_STORAGE_LITRES if size <= target)
    higher = min(size for size in STANDARD_STORAGE_LITRES if size > target)
    return lower, higher


def build_public_estimate(property_data, roof_data):
    point, distance = find_nearest_rainfall_point(
        roof_data['map_latitude'], roof_data['map_longitude']
    )
    if point is None:
        raise RainfallUnavailable(
            'Long-term rainfall data is unavailable for this location.'
        )

    area = Decimal(str(roof_data['area_m2']))
    annual_rainfall = Decimal(point.annual_rainfall_mm)
    runoff = RUNOFF_COEFFICIENTS[roof_data['roof_material']]
    gross_rainfall = (area * annual_rainfall).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )
    annual_harvest = calculate_yield_litres(
        area_m2=area,
        rainfall_mm=annual_rainfall,
        runoff_coefficient=runoff,
        system_efficiency=SYSTEM_EFFICIENCY,
    )
    storage_low, storage_high = _storage_range(annual_harvest)
    monthly_rainfall = normalise_monthly_rainfall(point.monthly_rainfall_mm)
    monthly_rows = []
    largest_yield = Decimal('0')
    for key, label in MONTHS:
        monthly_yield = calculate_yield_litres(
            area_m2=area,
            rainfall_mm=monthly_rainfall[key],
            runoff_coefficient=runoff,
            system_efficiency=SYSTEM_EFFICIENCY,
        )
        largest_yield = max(largest_yield, monthly_yield)
        monthly_rows.append(
            {
                'key': key,
                'month': label,
                'rainfall_mm': str(monthly_rainfall[key]),
                'yield_litres': str(monthly_yield),
            }
        )
    for row in monthly_rows:
        row['percentage'] = (
            int(
                (Decimal(row['yield_litres']) / largest_yield * 100).quantize(
                    Decimal('1'), rounding=ROUND_HALF_UP
                )
            )
            if largest_yield
            else 0
        )

    source = ' '.join(
        part for part in (point.source_name, point.source_version) if part
    )
    return {
        **property_data,
        'latitude': str(roof_data['map_latitude']),
        'longitude': str(roof_data['map_longitude']),
        'roof_area_m2': str(area),
        'roof_polygon': roof_data.get('polygon') or {},
        'roof_material': roof_data['roof_material'],
        'roof_material_label': dict(RoofSection.RoofMaterial.choices)[
            roof_data['roof_material']
        ],
        'intended_use': roof_data['intended_use'],
        'intended_use_label': dict(INTENDED_USE_CHOICES)[
            roof_data['intended_use']
        ],
        'has_existing_collection': roof_data['has_existing_collection'],
        'annual_rainfall_mm': str(annual_rainfall),
        'gross_rainfall_litres': str(gross_rainfall),
        'annual_harvest_litres': str(annual_harvest),
        'uncaptured_litres': (
            None
            if roof_data['has_existing_collection']
            else str(annual_harvest)
        ),
        'storage_low_litres': storage_low,
        'storage_high_litres': storage_high,
        'rainfall_source': source,
        'rainfall_reference_period': point.reference_period,
        'rainfall_distance_km': str(distance),
        'monthly_rows': monthly_rows,
    }
