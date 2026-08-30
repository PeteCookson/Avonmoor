from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('water_survey', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='RainfallGridPoint',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('grid_reference', models.CharField(max_length=80, unique=True)),
                ('latitude', models.DecimalField(db_index=True, decimal_places=6, max_digits=9)),
                ('longitude', models.DecimalField(db_index=True, decimal_places=6, max_digits=9)),
                ('monthly_rainfall_mm', models.JSONField()),
                ('annual_rainfall_mm', models.DecimalField(decimal_places=2, max_digits=7)),
                ('source_name', models.CharField(default='Met Office HadUK-Grid', max_length=120)),
                ('source_version', models.CharField(blank=True, max_length=40)),
                ('reference_period', models.CharField(default='1991-2020', max_length=20)),
                ('resolution_km', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('imported_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ['grid_reference']},
        ),
        migrations.AddField(
            model_name='survey',
            name='monthly_rainfall_mm',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='survey',
            name='rainfall_distance_km',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True),
        ),
        migrations.AddField(
            model_name='survey',
            name='rainfall_grid_point',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='surveys', to='water_survey.rainfallgridpoint'),
        ),
        migrations.AddField(
            model_name='survey',
            name='rainfall_reference_period',
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name='survey',
            name='rainfall_source',
            field=models.CharField(blank=True, max_length=180),
        ),
        migrations.AddField(
            model_name='survey',
            name='rainfall_updated_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='survey',
            name='annual_rainfall_mm',
            field=models.DecimalField(blank=True, decimal_places=2, help_text='Optional manual fallback when local climate data is unavailable.', max_digits=7, null=True),
        ),
        migrations.AddIndex(
            model_name='rainfallgridpoint',
            index=models.Index(fields=['latitude', 'longitude'], name='rain_grid_lat_lon_idx'),
        ),
    ]
