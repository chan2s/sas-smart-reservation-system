from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reservations", "0018_reservation_confirmation_email_claimed_at_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="reservation",
            name="organization_address",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="reservation",
            name="representative_position",
            field=models.CharField(blank=True, max_length=120),
        ),
    ]
