from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("facilities", "0005_alter_facility_built_ins"),
    ]

    operations = [
        migrations.AlterField(
            model_name="facility",
            name="facility_type",
            field=models.CharField(
                choices=[
                    ("GYMNASIUM", "Gymnasium"),
                    ("CAFETERIA", "Dorm Cafeteria"),
                    ("AVR", "Audio-Visual Room"),
                    ("MULTI_PURPOSE", "Multi-Purpose Hall"),
                    ("OUTDOOR", "Outdoor Area"),
                    ("OTHER", "Other"),
                ],
                default="OTHER",
                max_length=32,
            ),
        ),
    ]
