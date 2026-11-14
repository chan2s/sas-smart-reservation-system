from django.db import migrations, models
import reservations.models


def _paragraph(value, after=4):
    if not str(value or "").strip():
        return None
    return {
        "type": "paragraph",
        "attrs": {"spaceAfter": after},
        "content": [{"type": "text", "text": str(value).strip()}],
    }


def _line_paragraphs(value, after=4):
    return [node for line in str(value or "").splitlines() if (node := _paragraph(line, after))]


def _build_body(configuration):
    title = configuration.get("letter_title") or "RESERVATION APPROVAL LETTER"
    body = [
        {
            "type": "heading",
            "attrs": {"level": 1, "textAlign": "center", "spaceAfter": 4},
            "content": [{"type": "text", "text": title}],
        },
        {"type": "documentMetadata"},
        _paragraph("{{requester_name}}", 2),
        _paragraph("{{organization_name}}", 2),
        _paragraph("{{requester_email}}", 4),
        _paragraph("Dear {{requester_name}},", 5),
    ]
    body.extend(_line_paragraphs(configuration.get("introductory_paragraphs"), 3))
    body.extend(_line_paragraphs(configuration.get("approval_message"), 4))
    body.append({"type": "reservationDetails"})
    instructions = configuration.get("instructions_template", "")
    conditions = {
        "type": "heading",
        "attrs": {"level": 2, "textAlign": "left", "spaceAfter": 4},
        "content": [{"type": "text", "text": "Important instructions"}],
    }
    body.append(conditions)
    body.extend(_line_paragraphs(instructions, 2))
    body.append({"type": "reservationConditions"})
    body.extend(_line_paragraphs(configuration.get("additional_content"), 4))
    body.extend(_line_paragraphs(configuration.get("footer_disclaimer"), 1))
    return {"type": "doc", "content": [node for node in body if node is not None]}


def migrate_rich_bodies(apps, schema_editor):
    Settings = apps.get_model("reservations", "ApprovalLetterSettings")
    Version = apps.get_model("reservations", "ApprovalLetterTemplateVersion")
    for settings_row in Settings.objects.all().iterator():
        settings_row.body_content = _build_body({
            field: getattr(settings_row, field)
            for field in (
                "letter_title", "approval_message", "introductory_paragraphs",
                "instructions_template", "additional_content", "footer_disclaimer",
            )
        })
        settings_row.save(update_fields=("body_content",))

    for version in Version.objects.all().iterator():
        configuration = dict(version.configuration or {})
        configuration["body_content"] = _build_body(configuration)
        version.configuration = configuration
        version.save(update_fields=("configuration",))


class Migration(migrations.Migration):
    dependencies = [("reservations", "0032_approval_letter_staff_signature")]

    operations = [
        migrations.AddField(
            model_name="approvallettersettings",
            name="body_content",
            field=models.JSONField(default=reservations.models.default_approval_letter_body),
        ),
        migrations.RunPython(migrate_rich_bodies, migrations.RunPython.noop),
    ]
