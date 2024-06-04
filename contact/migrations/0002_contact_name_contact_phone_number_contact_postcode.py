# Generated by Django 5.0.6 on 2024-05-22 15:54

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contact', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='contact',
            name='name',
            field=models.CharField(default='Anonymous', max_length=255),
        ),
        migrations.AddField(
            model_name='contact',
            name='phone_number',
            field=models.CharField(default='000-000-0000', max_length=15),
        ),
        migrations.AddField(
            model_name='contact',
            name='postcode',
            field=models.CharField(default='00000', max_length=10),
        ),
    ]
