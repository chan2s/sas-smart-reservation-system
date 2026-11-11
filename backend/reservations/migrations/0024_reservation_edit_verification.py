from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("reservations", "0023_reservationevent_recipient_email"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ReservationEditVerification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("encrypted_payload", models.TextField()),
                ("otp_hash", models.CharField(max_length=256)),
                ("session_token_hash", models.CharField(max_length=64, unique=True)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("resend_available_at", models.DateTimeField()),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("requester", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reservation_edit_verifications", to=settings.AUTH_USER_MODEL)),
                ("reservation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="edit_verifications", to="reservations.reservation")),
            ],
        ),
        migrations.AddIndex(
            model_name="reservationeditverification",
            index=models.Index(fields=["reservation", "consumed_at"], name="reservation_reserva_38b2d1_idx"),
        ),
    ]
