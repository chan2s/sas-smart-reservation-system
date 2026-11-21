from django.db import migrations


REPLACEMENTS = (
    ("Student Affairs Services (SAS) Office", "General Services Office (GSO)"),
    ("STUDENT AFFAIRS AND SERVICES", "GENERAL SERVICES OFFICE"),
    ("Student Affairs and Services", "General Services Office"),
    ("SAS Office", "GSO Office"),
    ("SAS Staff", "GSO Staff"),
    ("SAS staff", "GSO staff"),
    ("SAS Administrator", "GSO Administrator"),
    ("SAS administrator", "GSO administrator"),
    ("SAS/UED", "GSO/UED"),
)


def update_knowledge_base(apps, schema_editor):
    Entry = apps.get_model("chatbot", "KnowledgeBaseEntry")
    for entry in Entry.objects.all().iterator():
        content = entry.content
        for old, new in REPLACEMENTS:
            content = content.replace(old, new)
        if content != entry.content:
            entry.content = content
            entry.save(update_fields=("content",))


class Migration(migrations.Migration):

    dependencies = [
        ("chatbot", "0002_knowledgebaseentry_visibility_and_more"),
    ]

    operations = [
        migrations.RunPython(update_knowledge_base, migrations.RunPython.noop),
    ]
