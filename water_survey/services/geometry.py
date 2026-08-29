import math
from decimal import Decimal, ROUND_HALF_UP


EARTH_RADIUS_M = 6371008.8


def _validate_position(position):
    if not isinstance(position, (list, tuple)) or len(position) < 2:
        raise ValueError('Each polygon point must contain longitude and latitude.')

    try:
        longitude = float(position[0])
        latitude = float(position[1])
    except (TypeError, ValueError):
        raise ValueError('Polygon coordinates must be numbers.') from None

    if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
        raise ValueError('Polygon coordinates are outside the valid range.')

    return longitude, latitude


def _ring_area_m2(ring):
    if not isinstance(ring, list):
        raise ValueError('Polygon rings must be lists of coordinates.')

    positions = [_validate_position(position) for position in ring]
    if len(positions) > 1 and positions[0] == positions[-1]:
        positions = positions[:-1]

    if len(set(positions)) < 3:
        raise ValueError('A roof outline needs at least three different points.')

    mean_latitude = math.radians(
        sum(latitude for _, latitude in positions) / len(positions)
    )
    projected = [
        (
            EARTH_RADIUS_M * math.radians(longitude) * math.cos(mean_latitude),
            EARTH_RADIUS_M * math.radians(latitude),
        )
        for longitude, latitude in positions
    ]

    twice_area = 0
    for index, (x1, y1) in enumerate(projected):
        x2, y2 = projected[(index + 1) % len(projected)]
        twice_area += (x1 * y2) - (x2 * y1)

    return abs(twice_area) / 2


def calculate_geojson_area_m2(geometry):
    """Return the horizontal area of a GeoJSON Polygon in square metres."""
    if not isinstance(geometry, dict) or geometry.get('type') != 'Polygon':
        raise ValueError('Roof outline must be a GeoJSON Polygon.')

    rings = geometry.get('coordinates')
    if not isinstance(rings, list) or not rings:
        raise ValueError('Roof outline does not contain any coordinates.')

    area = _ring_area_m2(rings[0])
    for hole in rings[1:]:
        area -= _ring_area_m2(hole)

    if area <= 0:
        raise ValueError('Roof outline must enclose an area greater than zero.')

    return Decimal(str(area)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
