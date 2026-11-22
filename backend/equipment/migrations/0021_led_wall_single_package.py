from decimal import Decimal

from django.db import migrations


def correct_led_wall_inventory(apps, schema_editor):
    """LED Wall is a single physical installation, not 100 separately reservable units.

    Total quantity is corrected from 100 to 1 and the counting unit changes from
    ``unit`` to ``package`` so inventory, availability, and admin all read as one
    complete rental package. Existing reservation items already use quantity = 1, so
    no reservation data is invalidated by this correction.
    """
    Equipment = apps.get_model("equipment", "Equipment")
    FacilityResource = apps.get_model("equipment", "FacilityResource")

    Equipment.objects.filter(is_active=True, name__iexact="LED Wall").update(
        total_quantity=1,
        unit="package",
    )

    FacilityResource.objects.filter(
        equipment__name__iexact="LED Wall"
    ).update(quantity=1)


def restore_led_wall_inventory(apps, schema_editor):
    """Reverse the correction.

    Quantity is restored to 100 and the unit is restored to ``unit``. Facility
    assignments that were touched by the forward migration are reverted to the
    legacy 0 (inherit equipment inventory). Reservation items are intentionally
    untouched in both directions.
    """
    Equipment = apps.get_model("equipment", "Equipment")
    FacilityResource = apps.get_model("equipment", "FacilityResource")

    Equipment.objects.filter(is_active=True, name__iexact="LED Wall").update(
        total_quantity=100,
        unit="unit",
    )

    FacilityResource.objects.filter(
        equipment__name__iexact="LED Wall"
    ).update(quantity=0)


class Migration(migrations.Migration):
    dependencies = [
        ("equipment", "0020_equipment_operator_fee_package_config"),
    ]

    operations = [
        migrations.RunPython(correct_led_wall_inventory, restore_led_wall_inventory),
    ]
