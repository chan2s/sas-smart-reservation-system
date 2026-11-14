from copy import deepcopy

from django.db import migrations


def add_contact_phone(apps, schema_editor):
    Settings = apps.get_model("reservations", "ApprovalLetterSettings")
    Version = apps.get_model("reservations", "ApprovalLetterTemplateVersion")

    def update(configuration):
        body = deepcopy(configuration.get("body_content") or {})
        content = body.get("content")
        if not isinstance(content, list):
            return configuration
        has_phone = any(
            node.get("type") == "paragraph"
            and "{{contact_phone}}" in "".join(
                child.get("text", "") for child in node.get("content", [])
                if child.get("type") == "text"
            )
            for node in content
        )
        if not has_phone:
            email_index = next((
                index for index, node in enumerate(content)
                if node.get("type") == "paragraph"
                and "{{requester_email}}" in "".join(
                    child.get("text", "") for child in node.get("content", [])
                    if child.get("type") == "text"
                )
            ), None)
            phone = {
                "type": "paragraph",
                "attrs": {"spaceAfter": 4},
                "content": [{"type": "text", "text": "{{contact_phone}}"}],
            }
            content.insert(email_index + 1 if email_index is not None else 2, phone)
            configuration["body_content"] = body
        return configuration

    for row in Settings.objects.all().iterator():
        configuration = update({"body_content": row.body_content})
        if configuration.get("body_content") != row.body_content:
            row.body_content = configuration["body_content"]
            row.save(update_fields=("body_content",))

    for row in Version.objects.all().iterator():
        configuration = update(dict(row.configuration or {}))
        if configuration != row.configuration:
            row.configuration = configuration
            row.save(update_fields=("configuration",))


class Migration(migrations.Migration):
    dependencies = [("reservations", "0033_approval_letter_rich_body")]

    operations = [migrations.RunPython(add_contact_phone, migrations.RunPython.noop)]
