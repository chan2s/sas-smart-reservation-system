"""Backfill the equipment image gallery from the legacy single image field.

Records created before the gallery existed store their picture in
``Equipment.image``. Each one becomes the primary (and only) gallery entry,
referencing the *same* stored file — no file is copied or moved. The
migration is idempotent: an equipment item that already has gallery images is
left untouched, so re-running it can never produce duplicates.
"""

from django.db import migrations


def copy_legacy_images(apps, schema_editor):
    Equipment = apps.get_model("equipment", "Equipment")
    EquipmentImage = apps.get_model("equipment", "EquipmentImage")

    legacy = Equipment.objects.exclude(image="").exclude(image__isnull=True).iterator()
    for equipment in legacy:
        if EquipmentImage.objects.filter(equipment_id=equipment.pk).exists():
            continue
        EquipmentImage.objects.create(
            equipment_id=equipment.pk,
            # Same storage name: a reference, not a copy of the file.
            image=equipment.image.name,
            caption="",
            display_order=0,
            is_primary=True,
        )


def drop_migrated_images(apps, schema_editor):
    """Reverse: drop the gallery rows that merely mirror the legacy field."""
    Equipment = apps.get_model("equipment", "Equipment")
    EquipmentImage = apps.get_model("equipment", "EquipmentImage")

    for equipment in Equipment.objects.exclude(image="").exclude(image__isnull=True).iterator():
        EquipmentImage.objects.filter(
            equipment_id=equipment.pk, image=equipment.image.name
        ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("equipment", "0003_equipmentimage"),
    ]

    operations = [
        migrations.RunPython(copy_legacy_images, drop_migrated_images),
    ]
