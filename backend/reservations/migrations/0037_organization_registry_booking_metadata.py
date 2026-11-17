import re
import unicodedata

import django.db.models.deletion
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
    text = unicodedata.normalize("NFKC", value or "").casefold()
    text = text.replace("&", " and ")
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    tokens = text.split(" ")
    while len(tokens) > 1 and tokens[-1] in IGNORED_TRAILING_WORDS:
        tokens.pop()
    return " ".join(tokens)[:200]


RESERVATION_TYPE_TO_ORGANIZATION = {
    "SCHOOL": "SCHOOL_UNIVERSITY",
    "GOVERNMENT": "GOVERNMENT_AGENCY",
    "PRIVATE": "PRIVATE_ORGANIZATION",
    "COMMUNITY": "COMMUNITY_ORGANIZATION",
    "NGO": "NGO",
    "OTHER": "OTHER",
    "": "OTHER",
}


def backfill_links_and_dates(apps, schema_editor):
    """Attach existing reservations to registry records and seed dates.

    Historical reservations are never renamed, deleted, or otherwise changed
    beyond filling a previously-empty ``organization_ref``. Organizations are
    NOT created here: only already-registered records are linked, so a data
    migration can never invent an organization from old free text. Each
    organization's last-reservation date is derived from its linked history.
    """
    Organization = apps.get_model("accounts", "Organization")
    Reservation = apps.get_model("reservations", "Reservation")

    registry = {}
    for organization in Organization.objects.all().only(
        "id", "organization_name", "organization_type"
    ):
        key = (
            normalize_name(organization.organization_name),
            organization.organization_type,
        )
        registry.setdefault(key, organization.id)

    latest = {}
    for reservation in Reservation.objects.exclude(organization_ref_id=None).only(
        "date", "organization_ref_id"
    ):
        current = latest.get(reservation.organization_ref_id)
        if current is None or reservation.date > current:
            latest[reservation.organization_ref_id] = reservation.date

    for reservation in Reservation.objects.filter(
        organization_ref_id=None
    ).exclude(organization="").only(
        "id", "organization", "organization_type", "requester_type", "date"
    ):
        if reservation.requester_type != "EXTERNAL":
            # Internal campus bookings already carry a managed organization
            # id; free-text legacy units are left untouched.
            continue
        key = (
            normalize_name(reservation.organization),
            RESERVATION_TYPE_TO_ORGANIZATION.get(
                reservation.organization_type, "OTHER"
            ),
        )
        organization_id = registry.get(key)
        if organization_id is None:
            continue
        Reservation.objects.filter(pk=reservation.id).update(
            organization_ref_id=organization_id
        )
        current = latest.get(organization_id)
        if current is None or reservation.date > current:
            latest[organization_id] = reservation.date

    for organization_id, last_date in latest.items():
        Organization.objects.filter(pk=organization_id).update(
            last_reservation_date=last_date
        )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0026_organization_registry_identity"),
        ("reservations", "0036_auto_payment_requirement"),
    ]

    operations = [
        migrations.AddField(
            model_name="reservation",
            name="submission_ip",
            field=models.GenericIPAddressField(
                blank=True,
                editable=False,
                help_text="Client IP at successful submission; staff-only metadata.",
                null=True,
            ),
        ),
        migrations.CreateModel(
            name="BookerLookupVerification",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("phone", models.CharField(db_index=True, max_length=20)),
                ("contact_person", models.CharField(blank=True, max_length=120)),
                ("contact_email", models.EmailField(blank=True, max_length=254)),
                ("otp_hash", models.CharField(max_length=256)),
                ("session_token_hash", models.CharField(max_length=64, unique=True)),
                (
                    "booker_token_hash",
                    models.CharField(blank=True, db_index=True, default="", max_length=64),
                ),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("resend_available_at", models.DateTimeField()),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="booker_lookup_verifications",
                        to="accounts.organization",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["phone", "consumed_at"],
                        name="reservation_phone_4ccf7e_idx",
                    )
                ],
            },
        ),
        migrations.RunPython(backfill_links_and_dates, migrations.RunPython.noop),
    ]
