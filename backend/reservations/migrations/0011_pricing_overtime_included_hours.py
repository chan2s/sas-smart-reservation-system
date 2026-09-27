"""Add the overtime fee type and align default rates with the SAS pricing rules.

The facility fee is a *flat* ₱5,000 covering the first 9 hours (the standard
8:00 AM–5:00 PM day). Overtime is ₱300 for every hour beyond that base, and the
sound-system operator is a ₱500 flat service charge. This migration adds the
schema needed to express those rules (``OVERTIME`` fee type + ``included_hours``)
and upgrades any already-seeded default rows so existing databases match.
"""

from decimal import Decimal

from django.db import migrations, models

OPERATOR_LABEL = "Sound System Operator"
OPERATOR_FLAT_PRICE = Decimal("500.00")
OVERTIME_PRICE = Decimal("300.00")
INCLUDED_HOURS = Decimal("9.00")

FACILITY_LABELS = {
    "GYMNASIUM": "Gymnasium Overtime",
    "CAFETERIA": "Cafeteria Overtime",
}

PRICING_RULE_FEE_TYPES = [
    ("FACILITY", "Facility fee"),
    ("OVERTIME", "Overtime fee"),
    ("EQUIPMENT", "Equipment fee"),
    ("OPERATOR", "Operator fee"),
]

RESERVATION_FEE_FEE_TYPES = [
    ("FACILITY", "Facility"),
    ("OVERTIME", "Overtime"),
    ("EQUIPMENT", "Equipment"),
    ("OPERATOR", "Operator"),
]


def apply_default_rates(apps, schema_editor):
    PricingRule = apps.get_model("reservations", "PricingRule")

    # Facility base fee covers the standard 9-hour day.
    PricingRule.objects.filter(
        fee_type="FACILITY", included_hours=Decimal("0.00")
    ).update(included_hours=INCLUDED_HOURS)

    # Operator service pay: ₱500 flat per reservation, not per hour.
    PricingRule.objects.filter(
        fee_type="OPERATOR", label=OPERATOR_LABEL, unit="hour"
    ).update(unit="flat", unit_price=OPERATOR_FLAT_PRICE)

    # One overtime rate per priced facility type (₱300/hour past the base).
    facility_types = (
        PricingRule.objects.filter(fee_type="FACILITY")
        .values_list("facility_type", flat=True)
        .distinct()
    )
    for facility_type in facility_types:
        if not facility_type:
            continue
        PricingRule.objects.get_or_create(
            fee_type="OVERTIME",
            facility_type=facility_type,
            defaults={
                "label": FACILITY_LABELS.get(
                    facility_type, f"{facility_type.title()} Overtime"
                ),
                "unit": "hour",
                "unit_price": OVERTIME_PRICE,
                "included_hours": INCLUDED_HOURS,
                "is_active": True,
            },
        )


def remove_overtime_rates(apps, schema_editor):
    PricingRule = apps.get_model("reservations", "PricingRule")
    PricingRule.objects.filter(fee_type="OVERTIME").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("reservations", "0010_reservation_organization_ref_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="pricingrule",
            name="fee_type",
            field=models.CharField(
                choices=PRICING_RULE_FEE_TYPES, db_index=True, max_length=16
            ),
        ),
        migrations.AddField(
            model_name="pricingrule",
            name="included_hours",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text=(
                    "Hours covered by the flat fee (facility rules) — or, for an "
                    "overtime rule, the base period it is measured against. E.g. 9 "
                    "for the standard 8:00 AM–5:00 PM facility day."
                ),
                max_digits=6,
            ),
        ),
        migrations.AlterField(
            model_name="reservationfee",
            name="fee_type",
            field=models.CharField(choices=RESERVATION_FEE_FEE_TYPES, max_length=16),
        ),
        migrations.RunPython(apply_default_rates, remove_overtime_rates),
    ]
