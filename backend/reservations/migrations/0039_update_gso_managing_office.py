from django.db import migrations


# Targeted replacements only: the project name "SAS RESERVE" is intentionally
# preserved, as are reservation references such as "SAS-2026-00001".
REPLACEMENTS = (
    ("Student Affairs Services (SAS) Office", "General Services Office (GSO)"),
    ("STUDENT AFFAIRS AND SERVICES", "GENERAL SERVICES OFFICE"),
    ("Student Affairs and Services", "General Services Office"),
    ("SAS Office", "GSO Office"),
    ("SAS Staff", "GSO Staff"),
    ("SAS staff", "GSO staff"),
    ("SAS Administrator", "GSO Administrator"),
    ("SAS Coordinator", "GSO Coordinator"),
    ("SAS/UED", "GSO/UED"),
)

TEXT_FIELDS = (
    "letter_title",
    "approval_message",
    "introductory_paragraphs",
    "instructions_template",
    "additional_content",
    "footer_disclaimer",
    "approval_label",
    "authorized_signatory_name",
    "credentials",
    "designation",
    "sas_staff_display_name",
    "sas_staff_designation",
)


def _replace(value):
    if isinstance(value, str):
        for old, new in REPLACEMENTS:
            value = value.replace(old, new)
        return value
    if isinstance(value, list):
        return [_replace(item) for item in value]
    if isinstance(value, dict):
        return {key: _replace(item) for key, item in value.items()}
    return value


def update_approval_letter_text(apps, schema_editor):
    Settings = apps.get_model("reservations", "ApprovalLetterSettings")
    Version = apps.get_model("reservations", "ApprovalLetterTemplateVersion")

    for row in Settings.objects.all():
        fields = []
        for field in TEXT_FIELDS:
            value = getattr(row, field)
            replacement = _replace(value)
            if replacement != value:
                setattr(row, field, replacement)
                fields.append(field)
        body = _replace(row.body_content)
        if body != row.body_content:
            row.body_content = body
            fields.append("body_content")
        if fields:
            row.save(update_fields=fields)

    for version in Version.objects.all().iterator():
        configuration = _replace(dict(version.configuration or {}))
        if configuration != version.configuration:
            version.configuration = configuration
            version.save(update_fields=("configuration",))


class Migration(migrations.Migration):

    dependencies = [
        ("reservations", "0038_reservation_assigned_operator_and_more"),
    ]

    operations = [
        migrations.RunPython(update_approval_letter_text, migrations.RunPython.noop),
    ]
