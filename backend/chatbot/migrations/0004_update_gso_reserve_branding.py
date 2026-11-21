from django.db import migrations


REPLACEMENTS = (
    ("SAS RESERVE", "GSO RESERVE"),
    ("SAS Reserve", "GSO Reserve"),
    ("sas reserve", "gso reserve"),
)


def _replace(value):
    if not isinstance(value, str):
        return value
    for old, new in REPLACEMENTS:
        value = value.replace(old, new)
    return value


def update_gso_reserve_branding(apps, schema_editor):
    Entry = apps.get_model("chatbot", "KnowledgeBaseEntry")
    for entry in Entry.objects.all().iterator():
        fields = []
        for field in ("title", "content", "keywords"):
            value = getattr(entry, field)
            replacement = _replace(value)
            if replacement != value:
                setattr(entry, field, replacement)
                fields.append(field)
        if fields:
            entry.save(update_fields=fields)


class Migration(migrations.Migration):

    dependencies = [
        ("chatbot", "0003_update_gso_managing_office"),
    ]

    operations = [
        migrations.RunPython(update_gso_reserve_branding, migrations.RunPython.noop),
    ]
