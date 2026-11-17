import re
import unicodedata

from django.db import migrations, models

IGNORED_TRAILING_WORDS = {
    "inc",
    "incorporated",
    "corp",
    "corporation",
    "co",
    "company",
    "ltd",
    "limited",
    "llc",
}


def normalize_name(value):
    """Copy of accounts.organization_registry.normalize_organization_name.

    Kept inline so the migration keeps producing the same values even if the
    runtime helper is tuned later.
    """
    text = unicodedata.normalize("NFKC", value or "").casefold()
    text = text.replace("&", " and ")
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    tokens = text.split(" ")
    while len(tokens) > 1 and tokens[-1] in IGNORED_TRAILING_WORDS:
        tokens.pop()
    return " ".join(tokens)[:200]


def populate_normalized_names(apps, schema_editor):
    Organization = apps.get_model("accounts", "Organization")
    seen = set()
    for organization in Organization.objects.order_by("created_at", "id").iterator():
        normalized = normalize_name(organization.organization_name)
        if normalized and (normalized, organization.organization_type) in seen:
            # Pre-existing duplicates keep their original name and record; only
            # the internal identity key is disambiguated so every historical
            # record survives while the unique constraint can be enforced.
            unique = f"{normalized} duplicate {organization.pk}"[:200]
            # Avoid a collision with a previously disambiguated key.
            suffix = 2
            while (unique, organization.organization_type) in seen:
                unique = f"{normalized} duplicate {organization.pk} {suffix}"[:200]
                suffix += 1
            normalized = unique
        seen.add((normalized, organization.organization_type))
        if organization.normalized_name != normalized:
            organization.normalized_name = normalized
            organization.save(update_fields=["normalized_name"])


def reverse_populate_normalized_names(apps, schema_editor):
    # Reversing only drops the derived field below; nothing to undo.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0025_remove_user_is_approval_signatory"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="normalized_name",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                editable=False,
                help_text="Normalized organization name used to prevent duplicates.",
                max_length=200,
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="last_reservation_date",
            field=models.DateField(
                blank=True,
                db_index=True,
                help_text="Date of the latest reservation linked to this organization.",
                null=True,
            ),
        ),
        migrations.RunPython(
            populate_normalized_names, reverse_populate_normalized_names
        ),
        migrations.AddConstraint(
            model_name="organization",
            constraint=models.UniqueConstraint(
                condition=~models.Q(normalized_name=""),
                fields=("normalized_name", "organization_type"),
                name="unique_organization_normalized_name_type",
            ),
        ),
    ]
