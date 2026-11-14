from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def create_baseline_template_version(apps, schema_editor):
    Settings = apps.get_model("reservations", "ApprovalLetterSettings")
    Version = apps.get_model("reservations", "ApprovalLetterTemplateVersion")
    settings_row, _ = Settings.objects.get_or_create(pk=1)
    fields = (
        "authorized_signatory_name", "credentials", "designation", "approval_label",
        "letter_title", "approval_message", "introductory_paragraphs",
        "instructions_template", "additional_content", "footer_disclaimer",
    )
    Version.objects.get_or_create(
        version=1,
        defaults={
            "configuration": {field: getattr(settings_row, field) for field in fields},
            "change_note": "Baseline configuration",
        },
    )


def preserve_template_history(apps, schema_editor):
    # Configuration history is intentionally retained on migration rollback.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("reservations", "0030_approval_letter_settings"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="approvallettersettings",
            name="letter_title",
            field=models.CharField(default="RESERVATION APPROVAL LETTER", max_length=140),
        ),
        migrations.AddField(
            model_name="approvallettersettings",
            name="approval_message",
            field=models.TextField(
                default=(
                    "This is to inform you that your request to use the "
                    "{{facility_name}} for {{event_name}} has been approved, subject to "
                    "the reservation details and conditions stated below."
                )
            ),
        ),
        migrations.AddField(
            model_name="approvallettersettings",
            name="introductory_paragraphs",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="approvallettersettings",
            name="instructions_template",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="approvallettersettings",
            name="additional_content",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="approvallettersettings",
            name="footer_disclaimer",
            field=models.TextField(blank=True),
        ),
        migrations.CreateModel(
            name="ApprovalLetterTemplateVersion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("version", models.PositiveIntegerField(unique=True)),
                ("configuration", models.JSONField()),
                ("change_note", models.CharField(blank=True, max_length=180)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("modified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="approval_letter_template_versions", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-version"]},
        ),
        migrations.RunPython(create_baseline_template_version, preserve_template_history),
    ]
