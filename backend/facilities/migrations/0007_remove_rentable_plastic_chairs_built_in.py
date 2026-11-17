"""Stop treating rentable Plastic Chairs as a built-in facility amenity.

Plastic Chairs are independently rentable inventory (300 pieces at PHP 5.00
each). The ``built_ins`` token ``"chairs"`` made the availability engine
classify every chair line as a built-in amenity and report 0 available,
regardless of the requested date/time window.

Remove only that token, and only at facilities where an active Plastic Chairs
resource is assigned (i.e. chairs are rentable there). ``"tables"`` is left
untouched: it is a separate amenity and no independently rentable table
inventory is configured. ``built_in_seats`` and every other facility field
are preserved.

Reversible: the reverse operation restores the ``"chairs"`` token on the same
facilities, returning them to their pre-fix configuration.
"""

from django.db import migrations

CHAIRS_TOKEN = "chairs"
PLASTIC_CHAIRS_NAME = "Plastic Chairs"


def _rentable_chairs_facility_ids(apps):
    """Facilities with an active Plastic Chairs resource assigned."""
    FacilityResource = apps.get_model("equipment", "FacilityResource")
    return set(
        FacilityResource.objects.filter(
            is_active=True,
            equipment__is_active=True,
            equipment__name__iexact=PLASTIC_CHAIRS_NAME,
        ).values_list("facility_id", flat=True)
    )


def _set_chairs_token(apps, *, present):
    Facility = apps.get_model("facilities", "Facility")
    facility_ids = _rentable_chairs_facility_ids(apps)
    for facility in Facility.objects.filter(pk__in=facility_ids).only(
        "pk", "built_ins"
    ):
        tokens = list(facility.built_ins or [])
        has_token = any(
            str(token).strip().lower() == CHAIRS_TOKEN for token in tokens
        )
        if present and has_token:
            continue
        if present:
            tokens.append(CHAIRS_TOKEN)
        elif has_token:
            tokens = [
                token
                for token in tokens
                if str(token).strip().lower() != CHAIRS_TOKEN
            ]
        else:
            continue
        facility.built_ins = tokens
        facility.save(update_fields=["built_ins"])


def remove_chairs_token(apps, schema_editor):
    _set_chairs_token(apps, present=False)


def restore_chairs_token(apps, schema_editor):
    _set_chairs_token(apps, present=True)


class Migration(migrations.Migration):

    dependencies = [
        ("facilities", "0006_cafeteria_catalog_label"),
        ("equipment", "0012_alter_equipment_price"),
    ]

    operations = [
        migrations.RunPython(remove_chairs_token, restore_chairs_token),
    ]
