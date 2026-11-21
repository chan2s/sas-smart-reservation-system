from django.db import migrations


REPLACEMENTS = (
    ("SAS RESERVE", "GSO RESERVE"),
    ("SAS Reserve", "GSO Reserve"),
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


def update_gso_reserve_branding(apps, schema_editor):
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
        ("reservations", "0039_update_gso_managing_office"),
    ]

    operations = [
        migrations.RunPython(update_gso_reserve_branding, migrations.RunPython.noop),
    ]
