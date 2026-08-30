from collections import OrderedDict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from math import asin, cos, radians, sin, sqrt

from django.db.models import Q
from django.utils import timezone


MONTHS = (
    ('jan', 'January'),
    ('feb', 'February'),
    ('mar', 'March'),
    ('apr', 'April'),
    ('may', 'May'),
    ('jun', 'June'),
    ('jul', 'July'),
    ('aug', 'August'),
    ('sep', 'September'),
    ('oct', 'October'),
    ('nov', 'November'),
    ('dec', 'December'),
)
MONTH_KEYS = tuple(key for key, _label in MONTHS)
DISTANCE_PRECISION = Decimal('0.01')


def normalise_monthly_rainfall(values):
    """Return ordered, validated monthly rainfall values as Decimals."""
    if not isinstance(values, dict):
        raise ValueError('Monthly rainfall must be an object with Jan-Dec values.')

    missing = [key for key in MONTH_KEYS if key not in values]
    extra = [key for key in values if key not in MONTH_KEYS]
    if missing or extra:
        raise ValueError('Monthly rainfall must contain exactly Jan-Dec values.')

    normalised = OrderedDict()
    for key in MONTH_KEYS:
        try:
            value = Decimal(str(values[key]))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise ValueError(f'{key.title()} rainfall must be a number.') from error
        if value < 0:
            raise ValueError(f'{key.title()} rainfall cannot be negative.')
        normalised[key] = value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return normalised


def serialise_monthly_rainfall(values):
    return {
        key: str(value)
        for key, value in normalise_monthly_rainfall(values).items()
    }


def haversine_distance_km(latitude_1, longitude_1, latitude_2, longitude_2):
    """Calculate great-circle distance between two WGS84 coordinates."""
    lat_1, lon_1, lat_2, lon_2 = map(
        radians,
        map(float, (latitude_1, longitude_1, latitude_2, longitude_2)),
    )
    delta_lat = lat_2 - lat_1
    delta_lon = lon_2 - lon_1
    haversine = (
        sin(delta_lat / 2) ** 2
        + cos(lat_1) * cos(lat_2) * sin(delta_lon / 2) ** 2
    )
    return 6371.0088 * 2 * asin(sqrt(haversine))


def find_nearest_rainfall_point(latitude, longitude, max_distance_km=30):
    """Find the closest cached grid point using an indexed bounding box."""
    from water_survey.models import RainfallGridPoint

    latitude = float(latitude)
    longitude = float(longitude)
    latitude_radius = max_distance_km / 110.574
    longitude_scale = max(cos(radians(latitude)), 0.1)
    longitude_radius = max_distance_km / (111.320 * longitude_scale)

    candidates = RainfallGridPoint.objects.filter(
        Q(latitude__gte=latitude - latitude_radius),
        Q(latitude__lte=latitude + latitude_radius),
        Q(longitude__gte=longitude - longitude_radius),
        Q(longitude__lte=longitude + longitude_radius),
    )

    nearest = None
    nearest_distance = None
    for candidate in candidates.iterator(chunk_size=1000):
        distance = haversine_distance_km(
            latitude,
            longitude,
            candidate.latitude,
            candidate.longitude,
        )
        if nearest_distance is None or distance < nearest_distance:
            nearest = candidate
            nearest_distance = distance

    if nearest is None or nearest_distance > max_distance_km:
        return None, None
    return nearest, Decimal(str(nearest_distance)).quantize(DISTANCE_PRECISION)


def apply_nearest_rainfall_to_survey(survey, max_distance_km=30):
    """Copy the nearest climatology values onto a geocoded survey."""
    if survey.latitude is None or survey.longitude is None:
        return None

    point, distance = find_nearest_rainfall_point(
        survey.latitude,
        survey.longitude,
        max_distance_km=max_distance_km,
    )
    if point is None:
        return None

    survey.rainfall_grid_point = point
    survey.monthly_rainfall_mm = point.monthly_rainfall_mm
    survey.annual_rainfall_mm = point.annual_rainfall_mm
    source_parts = [point.source_name, point.source_version]
    survey.rainfall_source = ' '.join(part for part in source_parts if part)
    survey.rainfall_reference_period = point.reference_period
    survey.rainfall_distance_km = distance
    survey.rainfall_updated_at = timezone.now()
    survey.save(
        update_fields=[
            'rainfall_grid_point',
            'monthly_rainfall_mm',
            'annual_rainfall_mm',
            'rainfall_source',
            'rainfall_reference_period',
            'rainfall_distance_km',
            'rainfall_updated_at',
            'updated_at',
        ]
    )
    return point
