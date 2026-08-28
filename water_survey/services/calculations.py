from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


LITRE_PRECISION = Decimal('0.01')


def _decimal(value, field_name):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f'{field_name} must be a number.') from exc


def calculate_yield_litres(
    *,
    area_m2,
    rainfall_mm,
    runoff_coefficient=Decimal('0.85'),
    system_efficiency=Decimal('0.95'),
):
    """Return harvested litres for a roof plan area and rainfall depth."""
    area = _decimal(area_m2, 'area_m2')
    rainfall = _decimal(rainfall_mm, 'rainfall_mm')
    runoff = _decimal(runoff_coefficient, 'runoff_coefficient')
    efficiency = _decimal(system_efficiency, 'system_efficiency')

    if area <= 0:
        raise ValueError('area_m2 must be greater than zero.')
    if rainfall < 0:
        raise ValueError('rainfall_mm cannot be negative.')
    if not Decimal('0') <= runoff <= Decimal('1'):
        raise ValueError('runoff_coefficient must be between 0 and 1.')
    if not Decimal('0') <= efficiency <= Decimal('1'):
        raise ValueError('system_efficiency must be between 0 and 1.')

    return (area * rainfall * runoff * efficiency).quantize(
        LITRE_PRECISION, rounding=ROUND_HALF_UP
    )


def calculate_monthly_yields(*, area_m2, monthly_rainfall_mm, **coefficients):
    """Calculate yield for an ordered mapping of month to rainfall depth."""
    return {
        month: calculate_yield_litres(
            area_m2=area_m2,
            rainfall_mm=rainfall,
            **coefficients,
        )
        for month, rainfall in monthly_rainfall_mm.items()
    }
