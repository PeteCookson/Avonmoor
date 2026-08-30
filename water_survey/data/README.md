# Rainfall grid import

The survey app uses a local cache of monthly long-term average rainfall. This
keeps survey calculations fast and repeatable and avoids a live dependency on a
large climate-data service.

Use the Met Office HadUK-Grid 1991-2020 rainfall climatology. HadUK-Grid is
available under the Open Government Licence and must be cited as instructed by
the CEDA dataset record.

Prepare a UTF-8 CSV with these required columns:

```text
grid_reference,latitude,longitude,jan,feb,mar,apr,may,jun,jul,aug,sep,oct,nov,dec
```

Optional columns are:

```text
source_name,source_version,reference_period,resolution_km
```

Coordinates must be WGS84 decimal degrees. Monthly values are millimetres. A
header-only example is provided in `rainfall_grid_example.csv`; it does not
contain invented climate data.

The repository includes an offline NetCDF converter. Run it on a local machine
after downloading the 1991-2020 monthly rainfall climatology from CEDA:

```bash
python -m pip install xarray numpy netCDF4
python scripts/prepare_haduk_rainfall.py /path/to/rainfall.nc \
  --output haduk_rainfall.csv \
  --source-version v1.3.2.ceda \
  --reference-period 1991-2020 \
  --resolution-km 1
```

The converter also accepts twelve single-month NetCDF files in January to
December order. Do not commit the resulting CSV or source NetCDF files; both are
ignored because they are deployment data rather than application source.

After deploying the code and running migrations:

```bash
python manage.py import_rainfall_grid /path/to/haduk_rainfall.csv --replace
```

Existing surveys retain copied rainfall values if the cache is replaced. Open a
survey and use **Refresh rainfall** to apply the newest imported values.

Authoritative source:

- https://www.metoffice.gov.uk/research/climate/maps-and-data/data/haduk-grid/datasets
- https://catalogue.ceda.ac.uk/uuid/4dc8450d889a491ebb20e724debe2dfb/
