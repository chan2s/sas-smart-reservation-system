from django.db import migrations, models


INITIAL_STAFF_NAME = "SAS Administrator"
INITIAL_STAFF_DESIGNATION = "UED Staff / SAS Staff"


def seed_staff_configuration(apps, schema_editor):
    Settings = apps.get_model("reservations", "ApprovalLetterSettings")
    Version = apps.get_model("reservations", "ApprovalLetterTemplateVersion")
    settings_row, _ = Settings.objects.get_or_create(pk=1)
    if not settings_row.sas_staff_display_name:
        settings_row.sas_staff_display_name = INITIAL_STAFF_NAME
    if not settings_row.sas_staff_designation:
        settings_row.sas_staff_designation = INITIAL_STAFF_DESIGNATION
    settings_row.save(update_fields=("sas_staff_display_name", "sas_staff_designation"))

    # Earlier versions inherited these display strings from the fixed letter
    # layout. Include them in snapshots so restore remains deterministic.
    for version in Version.objects.all().iterator():
        configuration = dict(version.configuration or {})
        configuration.setdefault("sas_staff_display_name", settings_row.sas_staff_display_name)
        configuration.setdefault("sas_staff_designation", settings_row.sas_staff_designation)
        version.configuration = configuration
        version.save(update_fields=("configuration",))


class Migration(migrations.Migration):
    dependencies = [("reservations", "0031_approval_letter_template_management")]

    operations = [
        migrations.AddField(
            model_name="approvallettersettings",
            name="sas_staff_display_name",
            field=models.CharField(blank=True, default="", max_length=160),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="approvallettersettings",
            name="sas_staff_designation",
            field=models.CharField(blank=True, default="", max_length=120),
            preserve_default=False,
        ),
        migrations.RunPython(seed_staff_configuration, migrations.RunPython.noop),
    ]
