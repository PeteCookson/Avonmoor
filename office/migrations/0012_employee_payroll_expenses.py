from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('office', '0011_expense_business_percentage')]

    operations = [
        migrations.CreateModel(
            name='Employee',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('display_name', models.CharField(max_length=160)),
                ('payroll_reference', models.CharField(blank=True, help_text='Optional employee or payroll reference used by Primo.', max_length=80)),
                ('notes', models.TextField(blank=True)),
                ('active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['display_name', 'id']},
        ),
        migrations.AddField(
            model_name='expense',
            name='employee',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='expenses', to='office.employee'),
        ),
        migrations.AddField(
            model_name='expenseimportrule',
            name='employee',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='expense_import_rules', to='office.employee'),
        ),
        migrations.AlterField(
            model_name='expense',
            name='category',
            field=models.CharField(choices=[('materials', 'Materials and supplies'), ('tools', 'Tools and equipment'), ('fuel', 'Fuel and travel'), ('mileage', 'Personal vehicle mileage reimbursement'), ('waste', 'Waste disposal'), ('subcontractor', 'Subcontractors'), ('payroll', 'Payroll and wages'), ('insurance', 'Insurance and professional fees'), ('office', 'Office and administration'), ('other', 'Other')], default='materials', max_length=20),
        ),
        migrations.AlterField(
            model_name='expenseimportrule',
            name='category',
            field=models.CharField(choices=[('materials', 'Materials and supplies'), ('tools', 'Tools and equipment'), ('fuel', 'Fuel and travel'), ('mileage', 'Personal vehicle mileage reimbursement'), ('waste', 'Waste disposal'), ('subcontractor', 'Subcontractors'), ('payroll', 'Payroll and wages'), ('insurance', 'Insurance and professional fees'), ('office', 'Office and administration'), ('other', 'Other')], max_length=20),
        ),
    ]
