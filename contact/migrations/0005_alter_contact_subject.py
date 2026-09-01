from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contact', '0004_remove_contact_updated_at'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contact',
            name='subject',
            field=models.CharField(
                choices=[
                    ('Garden', 'Garden'),
                    ('Property', 'Property'),
                    ('Rainwater Harvesting', 'Rainwater Harvesting'),
                    ('Other', 'Other'),
                ],
                max_length=255,
            ),
        ),
    ]
