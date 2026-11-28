from django.db import migrations, models

import reservations.models


class Migration(migrations.Migration):

    dependencies = [
        ("reservations", "0045_routing_letter_document"),
    ]

    operations = [
        migrations.RenameField(
            model_name="reservation",
            old_name="generated_routing_letter_pdf",
            new_name="generated_gso_routing_letter_pdf",
        ),
        migrations.RenameField(
            model_name="reservation",
            old_name="generated_routing_letter_at",
            new_name="generated_gso_routing_letter_at",
        ),
        migrations.AddField(
            model_name="reservation",
            name="generated_cas_routing_letter_pdf",
            field=models.FileField(
                blank=True, upload_to=reservations.models.routing_letter_upload_path
            ),
        ),
        migrations.AddField(
            model_name="reservation",
            name="generated_cas_routing_letter_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When the current CAS routing letter PDF was last generated successfully.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="reservation",
            name="generated_cas_routing_letter_email_sent_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When the CAS routing letter email was successfully delivered.",
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="reservation",
            name="generated_gso_routing_letter_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When the current GSO routing letter PDF was last generated successfully.",
                null=True,
            ),
        ),
    ]
