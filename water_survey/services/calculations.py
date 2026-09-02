import calendar
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP


LITRE_PRECISION = Decimal('0.01')
STANDARD_STORAGE_LITRES = (
    500,
    1000,
    1500,
    2000,
    2500,
    3000,
    4000,
    5000,
    7500,
    10000,
    15000,
    20000,
    30000,
    50000,
)
SIZING_STORAGE_DAYS = Decimal('18')
MONTH_KEYS = (
    'jan',
    'feb',
    'mar',
    'apr',
    'may',
    'jun',
    'jul',
    'aug',
    'sep',
    'oct',
    'nov',
    'dec',
)


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


def normalise_monthly_demand(monthly_demand_litres):
    """Return a complete, validated 12-month demand mapping."""
    if not isinstance(monthly_demand_litres, dict):
        raise ValueError('monthly_demand_litres must be a mapping.')

    normalised = {}
    for month in MONTH_KEYS:
        value = _decimal(monthly_demand_litres.get(month, 0), month)
        if value < 0:
            raise ValueError(f'{month} demand cannot be negative.')
        normalised[month] = value.quantize(
            LITRE_PRECISION, rounding=ROUND_HALF_UP
        )
    return normalised


def calculate_preliminary_storage_litres(*, annual_yield, annual_demand):
    """Size 18 days of the lower annual yield or non-potable demand."""
    yield_litres = _decimal(annual_yield, 'annual_yield')
    demand_litres = _decimal(annual_demand, 'annual_demand')
    if yield_litres < 0 or demand_litres < 0:
        raise ValueError('Annual yield and demand cannot be negative.')
    if not yield_litres or not demand_litres:
        return None

    target = (
        min(yield_litres, demand_litres)
        * SIZING_STORAGE_DAYS
        / Decimal('365')
    )
    for capacity in STANDARD_STORAGE_LITRES:
        if Decimal(capacity) >= target:
            return capacity

    thousands = (target / Decimal('1000')).quantize(
        Decimal('1'), rounding=ROUND_CEILING
    )
    return int(thousands * Decimal('1000'))


def simulate_storage_balance(
    *, monthly_yield_litres, monthly_demand_litres, capacity_litres
):
    """Model an evenly distributed daily balance over a repeated climate year.

    Five repeated years allow the store level to settle. Results are returned
    for the final representative year and remain indicative rather than a
    substitute for a detailed time-series design.
    """
    capacity = _decimal(capacity_litres, 'capacity_litres')
    if capacity <= 0:
        raise ValueError('capacity_litres must be greater than zero.')

    yields = normalise_monthly_demand(monthly_yield_litres)
    demands = normalise_monthly_demand(monthly_demand_litres)
    storage = Decimal('0')
    final_rows = []

    for year_index in range(5):
        year_rows = []
        for month_index, month in enumerate(MONTH_KEYS, start=1):
            days = Decimal(calendar.monthrange(2025, month_index)[1])
            daily_yield = yields[month] / days
            daily_demand = demands[month] / days
            supplied = Decimal('0')
            overflow = Decimal('0')

            for _ in range(int(days)):
                available = storage + daily_yield
                if available > capacity:
                    overflow += available - capacity
                    storage = capacity
                else:
                    storage = available

                delivered = min(storage, daily_demand)
                storage -= delivered
                supplied += delivered

            year_rows.append({
                'key': month,
                'yield_litres': yields[month],
                'demand_litres': demands[month],
                'supplied_litres': supplied.quantize(LITRE_PRECISION),
                'shortfall_litres': (demands[month] - supplied).quantize(
                    LITRE_PRECISION
                ),
                'overflow_litres': overflow.quantize(LITRE_PRECISION),
                'closing_storage_litres': storage.quantize(LITRE_PRECISION),
            })

        if year_index == 4:
            final_rows = year_rows

    total_demand = sum(
        (row['demand_litres'] for row in final_rows), Decimal('0')
    )
    total_supplied = sum(
        (row['supplied_litres'] for row in final_rows), Decimal('0')
    )
    total_shortfall = sum(
        (row['shortfall_litres'] for row in final_rows), Decimal('0')
    )
    total_overflow = sum(
        (row['overflow_litres'] for row in final_rows), Decimal('0')
    )
    coverage = (
        (total_supplied / total_demand * Decimal('100')).quantize(
            Decimal('0.1'), rounding=ROUND_HALF_UP
        )
        if total_demand
        else None
    )

    return {
        'capacity_litres': int(capacity),
        'rows': final_rows,
        'annual_demand_litres': total_demand.quantize(LITRE_PRECISION),
        'annual_supplied_litres': total_supplied.quantize(LITRE_PRECISION),
        'annual_shortfall_litres': total_shortfall.quantize(LITRE_PRECISION),
        'annual_overflow_litres': total_overflow.quantize(LITRE_PRECISION),
        'demand_coverage_percent': coverage,
    }
