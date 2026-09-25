"""Backfill the facility image gallery from the legacy single image field.

Facilities created before the gallery existed store their picture in
``Facility.image``. Each one becomes the primary (and only) gallery entry,
referencing the *same* stored file — no file is copied or moved. The
migration is idempotent: a facility that already has gallery images is left
untouched, so re-running it can never produce duplicates.
"""

from django.db import migrations


def copy_legacy_images(apps, schema_editor):
    Facility = apps.get_model("facilities", "Facility")
    FacilityImage = apps.get_model("facilities", "FacilityImage")

    legacy = Facility.objects.exclude(image="").exclude(image__isnull=True).iterator()
    for facility in legacy:
        if FacilityImage.objects.filter(facility_id=facility.pk).exists():
            continue
        FacilityImage.objects.create(
            facility_id=facility.pk,
            # Same storage name: a reference, not a copy of the file.
            image=facility.image.name,
            order=0,
            is_primary=True,
        )


def drop_migrated_images(apps, schema_editor):
    """Reverse: drop the gallery rows that merely mirror the legacy field."""
    Facility = apps.get_model("facilities", "Facility")
    FacilityImage = apps.get_model("facilities", "FacilityImage")

    for facility in Facility.objects.exclude(image="").exclude(image__isnull=True).iterator():
        FacilityImage.objects.filter(
            facility_id=facility.pk, image=facility.image.name
        ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("facilities", "0002_facilityimage"),
    ]

    operations = [
        migrations.RunPython(copy_legacy_images, drop_migrated_images),
    ]
