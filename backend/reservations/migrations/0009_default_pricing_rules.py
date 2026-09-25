"""Seed the default external-organization pricing rates.

Only *facility* rates are created unconditionally here (they need no related
rows). Equipment/operator rates are attached to the equipment categories they
price, and are created only when those categories already exist — a migration
must never invent reference data that a fresh database's ``seed`` command
owns. A fresh deployment therefore starts with the two facility fees, and
``python manage.py seed`` fills in everything else (see seed command).

These are staff-editable defaults: changing a rate in Django admin does not
require a code change, and per the pricing snapshot the rates stored on an
existing ``ReservationFee`` never change retroactively.
"""

from decimal import Decimal

from django.db import migrations

FACILITY_RATES = [
    # (facility_type, label, unit_price)
    ("GYMNASIUM", "Gymnasium", Decimal("5000.00")),
    ("CAFETERIA", "Cafeteria", Decimal("5000.00")),
]

# (category_name, label, unit_price, unit)
EQUIPMENT_RATES = [
    ("Chairs", "Chairs", Decimal("5.00"), "unit"),
    ("Sound Systems", "Sound System", Decimal("1000.00"), "unit"),
]

# (category_name, label, unit_price, unit)
OPERATOR_RATES = [
    ("Sound Systems", "Sound System Operator", Decimal("5.00"), "hour"),
]


def seed_default_rates(apps, schema_editor):
    PricingRule = apps.get_model("reservations", "PricingRule")
    EquipmentCategory = apps.get_model("equipment", "EquipmentCategory")

    for facility_type, label, price in FACILITY_RATES:
        PricingRule.objects.get_or_create(
            fee_type="FACILITY",
            facility_type=facility_type,
            defaults={
                "label": label,
                "unit": "flat",
                "unit_price": price,
                "is_active": True,
            },
        )

    for category_name, label, price, unit in EQUIPMENT_RATES:
        category = EquipmentCategory.objects.filter(name=category_name).first()
        if category is None:
            continue
        PricingRule.objects.get_or_create(
            fee_type="EQUIPMENT",
            equipment_category=category,
            defaults={
                "label": label,
                "unit": unit,
                "unit_price": price,
                "is_active": True,
            },
        )

    for category_name, label, price, unit in OPERATOR_RATES:
        category = EquipmentCategory.objects.filter(name=category_name).first()
        if category is None:
            continue
        PricingRule.objects.get_or_create(
            fee_type="OPERATOR",
            equipment_category=category,
            defaults={
                "label": label,
                "unit": unit,
                "unit_price": price,
                "is_active": True,
            },
        )


def remove_default_rates(apps, schema_editor):
    """Reverse: drop the seeded defaults, leaving staff-created rates alone."""
    PricingRule = apps.get_model("reservations", "PricingRule")
    labels = (
        [label for _, label, _ in FACILITY_RATES]
        + [label for _, label, _, _ in EQUIPMENT_RATES]
        + [label for _, label, _, _ in OPERATOR_RATES]
    )
    PricingRule.objects.filter(label__in=labels).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("equipment", "0004_copy_legacy_equipment_images"),
        ("reservations", "0008_reservation_estimated_total_reservationfee_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_default_rates, remove_default_rates),
    ]
