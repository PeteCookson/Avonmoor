from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('water_survey', '0002_rainfall_grid'),
    ]

    operations = [
        migrations.AlterField(
            model_name='roofsection',
            name='polygon',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='GeoJSON roof outline captured by the map tool.',
            ),
        ),
        migrations.CreateModel(
            name='SystemAssessment',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                ('intended_uses', models.JSONField(default=list)),
                (
                    'demand_basis',
                    models.CharField(
                        choices=[
                            ('customer', 'Customer estimate'),
                            ('fixture', 'Fixture and usage estimate'),
                            ('metered', 'Measured or metered use'),
                            ('other', 'Other evidence'),
                        ],
                        default='customer',
                        max_length=20,
                    ),
                ),
                (
                    'occupants',
                    models.PositiveSmallIntegerField(blank=True, null=True),
                ),
                ('monthly_demand_litres', models.JSONField(default=dict)),
                (
                    'tank_location',
                    models.CharField(
                        choices=[
                            ('unassessed', 'Not assessed'),
                            ('above_ground', 'Above ground'),
                            ('below_ground', 'Below ground'),
                            ('internal', 'Inside an outbuilding'),
                            ('mixed', 'Combined storage locations'),
                        ],
                        default='unassessed',
                        max_length=20,
                    ),
                ),
                (
                    'system_type',
                    models.CharField(
                        choices=[
                            ('unassessed', 'Not assessed'),
                            ('gravity', 'Gravity-fed above-ground system'),
                            ('above_pumped', 'Pumped above-ground system'),
                            ('below_pumped', 'Pumped below-ground system'),
                            ('header_tank', 'Pumped system with header tank'),
                            ('bespoke', 'Bespoke or commercial system'),
                        ],
                        default='unassessed',
                        max_length=20,
                    ),
                ),
                (
                    'access_rating',
                    models.CharField(
                        choices=[
                            ('unassessed', 'Not assessed'),
                            ('good', 'Good plant and delivery access'),
                            ('restricted', 'Restricted access'),
                            ('hand_dig', 'Hand excavation likely'),
                            (
                                'specialist',
                                'Specialist lifting or excavation required',
                            ),
                        ],
                        default='unassessed',
                        max_length=20,
                    ),
                ),
                (
                    'site_constraints',
                    models.JSONField(blank=True, default=list),
                ),
                (
                    'overflow_destination',
                    models.CharField(
                        choices=[
                            ('unassessed', 'Not assessed'),
                            ('soakaway', 'Soakaway or infiltration area'),
                            ('surface_water', 'Surface-water drainage'),
                            ('watercourse', 'Watercourse or pond'),
                            ('garden', 'Controlled discharge to garden'),
                            ('other', 'Other or requires investigation'),
                        ],
                        default='unassessed',
                        max_length=20,
                    ),
                ),
                (
                    'power_available',
                    models.CharField(
                        choices=[
                            ('unknown', 'Not assessed'),
                            ('yes', 'Suitable supply available'),
                            ('no', 'No suitable supply available'),
                        ],
                        default='unknown',
                        max_length=10,
                    ),
                ),
                (
                    'maximum_storage_litres',
                    models.PositiveIntegerField(blank=True, null=True),
                ),
                (
                    'proposed_storage_litres',
                    models.PositiveIntegerField(blank=True, null=True),
                ),
                ('route_notes', models.TextField(blank=True)),
                ('assessment_notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'survey',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='system_assessment',
                        to='water_survey.survey',
                    ),
                ),
            ],
            options={'ordering': ['-updated_at']},
        ),
    ]
