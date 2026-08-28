# Generated manually for the initial Avonmoor Water survey schema.
import decimal
import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Survey',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reference', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('property_name', models.CharField(blank=True, max_length=120)),
                ('address_line_1', models.CharField(max_length=160)),
                ('town', models.CharField(blank=True, max_length=100)),
                ('postcode', models.CharField(max_length=12)),
                ('latitude', models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ('longitude', models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
                ('annual_rainfall_mm', models.DecimalField(blank=True, decimal_places=2, help_text='Temporary manual value until the rainfall data import is connected.', max_digits=7, null=True)),
                ('status', models.CharField(choices=[('draft', 'Draft'), ('surveyed', 'Surveyed'), ('quoted', 'Quoted')], default='draft', max_length=12)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='water_surveys', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-updated_at']},
        ),
        migrations.CreateModel(
            name='RoofSection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(default='Main roof', max_length=80)),
                ('downpipe_label', models.CharField(blank=True, max_length=80)),
                ('roof_material', models.CharField(choices=[('metal', 'Metal or smooth sheet'), ('slate_tile', 'Slate or tile'), ('rough_tile', 'Rough concrete tile'), ('green', 'Green roof'), ('other', 'Other')], default='slate_tile', max_length=20)),
                ('area_m2', models.DecimalField(decimal_places=2, max_digits=8)),
                ('runoff_coefficient', models.DecimalField(decimal_places=3, default=decimal.Decimal('0.850'), help_text='Fraction of rainfall expected to run off the roof.', max_digits=4)),
                ('system_efficiency', models.DecimalField(decimal_places=3, default=decimal.Decimal('0.950'), help_text='Allowance for filters, first flush and other losses.', max_digits=4)),
                ('polygon', models.JSONField(blank=True, default=dict, help_text='GeoJSON roof outline. Populated by the map tool in the next stage.')),
                ('sort_order', models.PositiveSmallIntegerField(default=0)),
                ('survey', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='roof_sections', to='water_survey.survey')),
            ],
            options={'ordering': ['sort_order', 'id']},
        ),
    ]
