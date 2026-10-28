from django.db import migrations, models


def snapshot_existing_approvers(apps, schema_editor):
    ApprovalLetter = apps.get_model("approval_letters", "ApprovalLetter")
    db = schema_editor.connection.alias
    for letter in ApprovalLetter.objects.using(db).select_related("signatory").filter(
        signatory__isnull=False
    ).iterator():
        approver = letter.signatory
        full_name = " ".join(
            part for part in (approver.first_name, approver.last_name) if part
        ).strip()
        letter.signatory_name = full_name or approver.username
        letter.signatory_username = approver.username
        letter.signatory_email = approver.email or ""
        letter.save(
            using=db,
            update_fields=(
                "signatory_name",
                "signatory_username",
                "signatory_email",
            ),
        )


class Migration(migrations.Migration):
    dependencies = [
        ("approval_letters", "0004_approval_status"),
        ("accounts", "0024_active_assistant_campus_director_unique"),
    ]

    operations = [
        migrations.AddField(
            model_name="approvalletter",
            name="signatory_name",
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AddField(
            model_name="approvalletter",
            name="signatory_username",
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.AddField(
            model_name="approvalletter",
            name="signatory_email",
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.RunPython(snapshot_existing_approvers, migrations.RunPython.noop),
    ]
