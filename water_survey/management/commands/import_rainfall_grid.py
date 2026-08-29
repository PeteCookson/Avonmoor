import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from water_survey.models import RainfallGridPoint
from water_survey.services.rainfall import MONTH_KEYS, serialise_monthly_rainfall


REQUIRED_COLUMNS = {
    'grid_reference',
    'latitude',
    'longitude',
    *MONTH_KEYS,
}
UPSERT_FIELDS = [
    'latitude',
    'longitude',
    'monthly_rainfall_mm',
    'annual_rainfall_mm',
    'source_name',
    'source_version',
    'reference_period',
    'resolution_km',
]


class Command(BaseCommand):
    help = 'Import a prepared monthly rainfall climatology CSV into the local cache.'

    def add_arguments(self, parser):
        parser.add_argument('csv_path', type=Path)
        parser.add_argument(
            '--replace',
            action='store_true',
            help='Delete existing rainfall grid points before importing.',
        )
        parser.add_argument('--batch-size', type=int, default=1000)

    def handle(self, *args, **options):
        csv_path = options['csv_path'].expanduser().resolve()
        if not csv_path.is_file():
            raise CommandError(f'CSV file not found: {csv_path}')
        if options['batch_size'] < 1:
            raise CommandError('--batch-size must be greater than zero.')

        points = self._read_points(csv_path)
        if not points:
            raise CommandError('The CSV contains no rainfall grid points.')

        with transaction.atomic():
            if options['replace']:
                deleted, _details = RainfallGridPoint.objects.all().delete()
                self.stdout.write(f'Removed {deleted} existing rainfall records.')

            RainfallGridPoint.objects.bulk_create(
                points,
                batch_size=options['batch_size'],
                update_conflicts=True,
                update_fields=UPSERT_FIELDS,
                unique_fields=['grid_reference'],
            )

        self.stdout.write(
            self.style.SUCCESS(f'Imported {len(points)} rainfall grid points.')
        )

    def _read_points(self, csv_path):
        points = []
        references = set()
        with csv_path.open(newline='', encoding='utf-8-sig') as csv_file:
            reader = csv.DictReader(csv_file)
            columns = set(reader.fieldnames or [])
            missing = sorted(REQUIRED_COLUMNS - columns)
            if missing:
                raise CommandError(
                    f'CSV is missing required columns: {", ".join(missing)}'
                )

            for row_number, row in enumerate(reader, start=2):
                try:
                    grid_reference = row['grid_reference'].strip()
                    if not grid_reference:
                        raise ValueError('grid_reference is empty')
                    if grid_reference in references:
                        raise ValueError(
                            f'duplicate grid_reference {grid_reference!r}'
                        )
                    references.add(grid_reference)

                    latitude = self._decimal(row['latitude'], 'latitude')
                    longitude = self._decimal(row['longitude'], 'longitude')
                    if not Decimal('-90') <= latitude <= Decimal('90'):
                        raise ValueError('latitude must be between -90 and 90')
                    if not Decimal('-180') <= longitude <= Decimal('180'):
                        raise ValueError('longitude must be between -180 and 180')

                    monthly = serialise_monthly_rainfall(
                        {key: row[key] for key in MONTH_KEYS}
                    )
                    annual = sum(
                        (Decimal(value) for value in monthly.values()),
                        Decimal('0'),
                    )
                    resolution = row.get('resolution_km', '').strip()
                    points.append(
                        RainfallGridPoint(
                            grid_reference=grid_reference,
                            latitude=latitude,
                            longitude=longitude,
                            monthly_rainfall_mm=monthly,
                            annual_rainfall_mm=annual,
                            source_name=(
                                row.get('source_name', '').strip()
                                or 'Met Office HadUK-Grid'
                            ),
                            source_version=row.get('source_version', '').strip(),
                            reference_period=(
                                row.get('reference_period', '').strip()
                                or '1991-2020'
                            ),
                            resolution_km=(
                                self._decimal(resolution, 'resolution_km')
                                if resolution
                                else None
                            ),
                        )
                    )
                except (InvalidOperation, TypeError, ValueError) as error:
                    raise CommandError(f'Row {row_number}: {error}') from error
        return points

    @staticmethod
    def _decimal(value, field_name):
        try:
            return Decimal(str(value).strip())
        except (InvalidOperation, TypeError, ValueError) as error:
            raise ValueError(f'{field_name} must be a number') from error
