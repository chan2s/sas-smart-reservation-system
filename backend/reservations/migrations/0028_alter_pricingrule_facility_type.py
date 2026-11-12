from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("facilities", "0006_cafeteria_catalog_label"),
        ("reservations", "0027_unified_rental_catalog"),
    ]

    operations = [
        migrations.AlterField(
            model_name="pricingrule",
            name="facility_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("GYMNASIUM", "Gymnasium"),
                    ("CAFETERIA", "Dorm Cafeteria"),
                    ("AVR", "Audio-Visual Room"),
                    ("MULTI_PURPOSE", "Multi-Purpose Hall"),
                    ("OUTDOOR", "Outdoor Area"),
                    ("OTHER", "Other"),
                ],
                help_text="For facility fees: which facility type this rate covers.",
                max_length=32,
            ),
        ),
    ]
