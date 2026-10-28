from django.db import migrations, models


def preserve_approved_letters(apps, schema_editor):
    ApprovalLetter = apps.get_model("approval_letters", "ApprovalLetter")
    ApprovalLetter.objects.filter(
        status__in=("SIGNED", "SENT", "EMAIL_FAILED")
    ).update(status="APPROVED")


def restore_legacy_letter_states(apps, schema_editor):
    ApprovalLetter = apps.get_model("approval_letters", "ApprovalLetter")
    approved = ApprovalLetter.objects.filter(status="APPROVED")
    approved.filter(email_status="SENT").update(status="SENT")
    approved.filter(email_status="FAILED").update(status="EMAIL_FAILED")
    approved.exclude(email_status__in=("SENT", "FAILED")).update(status="SIGNED")


class Migration(migrations.Migration):
    dependencies = [("approval_letters", "0003_alter_approvalletter_email_status")]

    operations = [
        migrations.AlterField(
            model_name="approvalletter",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING_SIGNATURE", "Pending signature"),
                    ("APPROVED", "Approved"),
                    ("SIGNED", "Signed (legacy)"),
                    ("SENT", "Signed and sent (legacy)"),
                    ("EMAIL_FAILED", "Signed — email failed (legacy)"),
                ],
                db_index=True,
                default="PENDING_SIGNATURE",
                max_length=20,
            ),
        ),
        migrations.RunPython(
            preserve_approved_letters,
            restore_legacy_letter_states,
        ),
    ]
