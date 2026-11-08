from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0003_notification_event_key_push_devices"),
    ]

    operations = [
        migrations.AddField(
            model_name="pushsubscription",
            name="app_origin",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
