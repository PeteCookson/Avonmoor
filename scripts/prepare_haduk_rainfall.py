#!/usr/bin/env python3
"""Convert HadUK-Grid monthly climatology NetCDF data to the app CSV format.

This is an offline data-preparation utility. xarray and numpy are intentionally
not application dependencies; install them only in the environment used to
prepare the import file.
"""

import argparse
import csv
import sys
from pathlib import Path


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


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            'Convert one 12-month or twelve single-month HadUK-Grid rainfall '
            'NetCDF files into the Avonmoor rainfall CSV format.'
        )
    )
    parser.add_argument('netcdf', nargs='+', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--source-version', required=True)
    parser.add_argument('--reference-period', default='1991-2020')
    parser.add_argument('--resolution-km', type=float, required=True)
    return parser.parse_args()


def load_modules():
    try:
        import numpy as np
        import xarray as xr
    except ImportError as error:
        raise SystemExit(
            'This converter requires xarray, numpy and a NetCDF engine. '
            'Install them with: pip install xarray numpy netCDF4'
        ) from error
    return np, xr


def find_coordinate(dataset, names):
    for name in names:
        if name in dataset.variables:
            return dataset[name]
    raise ValueError(f'NetCDF is missing a coordinate named {" or ".join(names)}.')


def rainfall_array(dataset, np):
    if 'rainfall' not in dataset.data_vars:
        raise ValueError('NetCDF does not contain a rainfall data variable.')
    data = dataset['rainfall'].squeeze(drop=True)
    spatial_dims = {
        dim
        for dim in data.dims
        if dim in {'projection_y_coordinate', 'projection_x_coordinate', 'y', 'x'}
    }
    month_dims = [dim for dim in data.dims if dim not in spatial_dims]
    if len(month_dims) != 1 or data.sizes[month_dims[0]] != 12:
        raise ValueError(
            'Expected one 12-month dimension plus the two spatial dimensions.'
        )
    month_dim = month_dims[0]
    y_dim = next((dim for dim in data.dims if dim.endswith('y_coordinate')), 'y')
    x_dim = next((dim for dim in data.dims if dim.endswith('x_coordinate')), 'x')
    if y_dim not in data.dims or x_dim not in data.dims:
        raise ValueError('Could not identify the NetCDF x and y dimensions.')
    return np.asarray(data.transpose(month_dim, y_dim, x_dim).values, dtype=float)


def load_data(paths, np, xr):
    datasets = [xr.open_dataset(path) for path in paths]
    try:
        first = datasets[0]
        latitude = np.asarray(
            find_coordinate(first, ('latitude', 'lat')).values,
            dtype=float,
        )
        longitude = np.asarray(
            find_coordinate(first, ('longitude', 'lon')).values,
            dtype=float,
        )
        if len(datasets) == 1:
            rainfall = rainfall_array(first, np)
        elif len(datasets) == 12:
            monthly = []
            for dataset in datasets:
                values = np.asarray(
                    dataset['rainfall'].squeeze(drop=True).values,
                    dtype=float,
                )
                if values.ndim != 2:
                    raise ValueError(
                        'Each single-month NetCDF rainfall array must be 2D.'
                    )
                monthly.append(values)
            rainfall = np.stack(monthly, axis=0)
        else:
            raise ValueError('Supply either one 12-month file or 12 monthly files.')

        if latitude.ndim == 1 and longitude.ndim == 1:
            longitude, latitude = np.meshgrid(longitude, latitude)
        if latitude.shape != rainfall.shape[1:] or longitude.shape != rainfall.shape[1:]:
            raise ValueError('Latitude/longitude coordinates do not match the grid.')

        x_coordinate = find_coordinate(
            first, ('projection_x_coordinate', 'x')
        ).values
        y_coordinate = find_coordinate(
            first, ('projection_y_coordinate', 'y')
        ).values
        return rainfall, latitude, longitude, x_coordinate, y_coordinate
    finally:
        for dataset in datasets:
            dataset.close()


def write_csv(args, np, rainfall, latitude, longitude, x_coordinate, y_coordinate):
    args.output.parent.mkdir(parents=True, exist_ok=True)
    headers = [
        'grid_reference',
        'latitude',
        'longitude',
        *MONTH_KEYS,
        'source_name',
        'source_version',
        'reference_period',
        'resolution_km',
    ]
    valid = np.isfinite(rainfall).all(axis=0)
    written = 0
    with args.output.open('w', newline='', encoding='utf-8') as output_file:
        writer = csv.writer(output_file)
        writer.writerow(headers)
        for row_index, column_index in zip(*np.where(valid)):
            x_value = float(x_coordinate[column_index])
            y_value = float(y_coordinate[row_index])
            writer.writerow(
                [
                    f'{int(round(x_value))}-{int(round(y_value))}',
                    f'{latitude[row_index, column_index]:.6f}',
                    f'{longitude[row_index, column_index]:.6f}',
                    *(f'{value:.2f}' for value in rainfall[:, row_index, column_index]),
                    'Met Office HadUK-Grid',
                    args.source_version,
                    args.reference_period,
                    f'{args.resolution_km:g}',
                ]
            )
            written += 1
    return written


def main():
    args = parse_args()
    missing = [str(path) for path in args.netcdf if not path.is_file()]
    if missing:
        raise SystemExit(f'NetCDF file not found: {missing[0]}')
    np, xr = load_modules()
    try:
        data = load_data(args.netcdf, np, xr)
        written = write_csv(args, np, *data)
    except (KeyError, ValueError) as error:
        raise SystemExit(str(error)) from error
    print(f'Wrote {written} rainfall grid points to {args.output}')


if __name__ == '__main__':
    main()
