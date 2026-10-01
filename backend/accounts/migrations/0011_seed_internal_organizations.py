"""Seed the nine official internal NORSU organizations.

Internal organizations (CAS, CTED, CRIM, CIT, CBA, CAF, CARE, GHAD, CSSG) are
managed reference data, not free text. They are keyed by their acronym, which
doubles as the unique ``organization_code``, so re-running migrations never
creates duplicates and never rewrites an existing record.

CARE / GHAD / CSSG intentionally keep their acronym as their name — their
expanded names were not provided.

The ``seed`` management command applies the same list for a fresh deployment.
"""

from django.db import migrations

INTERNAL_ORGANIZATIONS = (
    ("CAS", "College of Arts and Sciences"),
    ("CTED", "College of Teacher Education"),
    ("CRIM", "College of Criminology and Justice"),
    ("CIT", "College of Industrial Technology"),
    ("CBA", "College of Business Administration"),
    ("CAF", "College of Agricultural and Forestry"),
    ("CARE", "CARE"),
    ("GHAD", "GHAD"),
    ("CSSG", "CSSG"),
)


def seed_internal_organizations(apps, schema_editor):
    Organization = apps.get_model("accounts", "Organization")

    for acronym, name in INTERNAL_ORGANIZATIONS:
        organization, created = Organization.objects.get_or_create(
            organization_code=acronym,
            defaults={
                "acronym": acronym,
                "organization_name": name,
                "organization_type": "INTERNAL",
                "verification_status": "APPROVED",
                "is_active": True,
                "contact_person": name,
                "contact_email": "",
            },
        )
        # Idempotent backfill only: never overwrite data staff may have
        # edited, and never reactivate a deliberately deactivated record.
        if not created and not organization.acronym:
            organization.acronym = acronym
            organization.save(update_fields=["acronym"])


def remove_internal_organizations(apps, schema_editor):
    """Reverse: remove the seeded internal organizations by their code.

    Users/reservations referencing them are set to NULL by the FK's
    ``SET_NULL`` behavior, so historical rows are preserved.
    """
    Organization = apps.get_model("accounts", "Organization")
    codes = [acronym for acronym, _ in INTERNAL_ORGANIZATIONS]
    Organization.objects.filter(
        organization_code__in=codes, organization_type="INTERNAL"
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0010_alter_organization_options_organization_acronym_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_internal_organizations, remove_internal_organizations),
    ]
