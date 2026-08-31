from django.db import migrations, models
import uuid


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='CustomerSurveyLead',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reference', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('status', models.CharField(choices=[('new', 'New'), ('contacted', 'Contacted'), ('qualified', 'Qualified'), ('closed', 'Closed')], default='new', max_length=12)),
                ('name', models.CharField(max_length=120)),
                ('email', models.EmailField(max_length=254)),
                ('phone', models.CharField(blank=True, max_length=30)),
                ('preferred_contact', models.CharField(choices=[('email', 'Email'), ('phone', 'Phone')], default='email', max_length=10)),
                ('address_line_1', models.CharField(max_length=160)),
                ('town', models.CharField(blank=True, max_length=100)),
                ('postcode', models.CharField(max_length=12)),
                ('latitude', models.DecimalField(decimal_places=6, max_digits=9)),
                ('longitude', models.DecimalField(decimal_places=6, max_digits=9)),
                ('roof_area_m2', models.DecimalField(decimal_places=2, max_digits=8)),
                ('roof_polygon', models.JSONField(blank=True, default=dict)),
                ('roof_material', models.CharField(choices=[('metal', 'Metal or smooth sheet'), ('slate_tile', 'Slate or tile'), ('rough_tile', 'Rough concrete tile'), ('green', 'Green roof'), ('other', 'Other')], max_length=20)),
                ('intended_use', models.CharField(choices=[('garden', 'Garden watering'), ('garden_vehicles', 'Garden and vehicle washing'), ('home', 'Toilets and washing machine'), ('rural', 'Livestock, rural or commercial use'), ('unsure', 'Not sure yet')], max_length=30)),
                ('has_existing_collection', models.BooleanField(default=False)),
                ('annual_rainfall_mm', models.DecimalField(decimal_places=2, max_digits=7)),
                ('estimated_annual_harvest_litres', models.DecimalField(decimal_places=2, max_digits=12)),
                ('indicative_storage_low_litres', models.PositiveIntegerField()),
                ('indicative_storage_high_litres', models.PositiveIntegerField(null=True)),
                ('rainfall_source', models.CharField(max_length=180)),
                ('rainfall_reference_period', models.CharField(max_length=20)),
                ('customer_message', models.TextField(blank=True)),
                ('consented_at', models.DateTimeField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
