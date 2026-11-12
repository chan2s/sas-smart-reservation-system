from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("equipment", "0010_maintenancerecord_unique_open_report_per_equipment_reporter"),
    ]

    operations = [
        migrations.AddField(
            model_name="equipmentcategory",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
    ]
