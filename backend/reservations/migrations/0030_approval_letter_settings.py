from django.conf import settings
from django.db import migrations, models


def migrate_existing_authorized_signatory(apps, schema_editor):
    """Preserve the current role-based signatory when an account exists."""
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    Configuration = apps.get_model("reservations", "ApprovalLetterSettings")
    current = User.objects.filter(
        role="ASSISTANT_CAMPUS_DIRECTOR_ADMIN_FINANCE", is_active=True
    ).order_by("id").first()
    if current is None:
        return
    full_name = " ".join(part for part in (current.first_name, current.last_name) if part).strip()
    full_name = full_name or current.username
    designation = current.get_role_display()
    Configuration.objects.update_or_create(
        pk=1,
        defaults={
            "authorized_signatory_name": full_name,
            "designation": designation,
        },
    )


def keep_migrated_signatory(apps, schema_editor):
    # Rollback leaves user-managed configuration intact.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0025_remove_user_is_approval_signatory"),
        ("reservations", "0029_reservation_approval_email_attempts_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ApprovalLetterSettings",
            fields=[
                ("id", models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
                ("authorized_signatory_name", models.CharField(blank=True, max_length=160)),
                ("credentials", models.CharField(blank=True, max_length=80)),
                ("designation", models.CharField(blank=True, max_length=180)),
                ("approval_label", models.CharField(default="Approved by:", max_length=80)),
            ],
            options={
                "verbose_name": "approval letter settings",
                "verbose_name_plural": "approval letter settings",
            },
        ),
        migrations.RunPython(migrate_existing_authorized_signatory, keep_migrated_signatory),
    ]
