from django.db import migrations


def seed(apps, schema_editor):
    apps.get_model('office', 'MileageLedger').objects.get_or_create(pk=1, defaults={
        'claimant': 'Pete Cookson', 'vehicle': 'Personally owned 2004 Ford Transit Connect'})


class Migration(migrations.Migration):
    dependencies = [('office', '0007_mileage_claims')]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
