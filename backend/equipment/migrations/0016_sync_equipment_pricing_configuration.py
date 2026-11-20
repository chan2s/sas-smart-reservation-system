"""Backfill equipment rental pricing configuration.

The pricing fields added in migration 0015 default to ``0.00``, which means
"not configured". Reservation pricing falls back to the legacy category
``PricingRule`` rates in that case, but the effective charge must stay exactly
what it was before the fields existed. This migration records those existing
rates on the equipment item itself, so Equipment Management becomes the
authoritative source without changing any amount that is currently charged.

Rules applied (data-driven; nothing is changed when the source is missing):

* the official catalog's period-priced item (LED Wall) becomes
  ``DURATION`` pricing, with its whole-day / half-day rates copied from the
  active period ``PricingRule`` rows (falling back to its legacy price);
* the official catalog's package item (Sound System) becomes ``PACKAGE``
  pricing, so its components are not charged individually; its operator fee
  continues to come from the existing operator ``PricingRule``;
* every other item keeps ``PER_UNIT`` pricing and gets ``unit_price`` from its
  legacy ``Equipment.price`` (or, for the official per-piece catalog item, from
  the active per-category rate) only when no unit price is configured yet.

Existing ``Equipment.price`` values are never overwritten, historical
reservations are untouched (fees are snapshotted on ``ReservationFee``), and
the reverse migration is a no-op because the previous state ("not configured")
is valid and cannot be distinguished safely.
"""

from decimal import Decimal

from django.db import migrations

#: Catalog items whose existing pricing basis is not plain per-unit.
DURATION_PRICED_ITEMS = {"led wall"}
PACKAGE_PRICED_ITEMS = {"sound system"}
#: Catalog items whose effective charge comes from the category rate rather
#: than from their legacy stored price.
CATEGORY_RATE_ITEMS = {"plastic chairs"}


def _category_rule(PricingRule, category_id, rental_period=None):
    if category_id is None:
        return None
    rows = PricingRule.objects.filter(
        is_active=True,
        fee_type="EQUIPMENT",
        equipment_category_id=category_id,
    )
    if rental_period is None:
        rows = rows.filter(rental_period="")
    else:
        rows = rows.filter(rental_period=rental_period)
    return rows.order_by("id").first()


def sync_equipment_pricing(apps, schema_editor):
    Equipment = apps.get_model("equipment", "Equipment")
    PricingRule = apps.get_model("reservations", "PricingRule")

    for equipment in Equipment.objects.all().iterator():
        name = (equipment.name or "").strip().casefold()
        updates = {}

        if name in DURATION_PRICED_ITEMS:
            whole_rule = _category_rule(PricingRule, equipment.category_id, "WHOLE_DAY")
            half_rule = _category_rule(PricingRule, equipment.category_id, "HALF_DAY")
            whole_day = (
                whole_rule.unit_price
                if whole_rule is not None and whole_rule.unit_price > 0
                else equipment.price
            )
            if whole_day <= 0:
                continue
            half_day = (
                half_rule.unit_price
                if half_rule is not None and half_rule.unit_price > 0
                else (whole_day / 2).quantize(Decimal("0.01"))
            )
            updates.update(
                pricing_method="DURATION",
                whole_day_price=whole_day,
                half_day_price=half_day,
                hourly_rate=Decimal("0.00"),
            )
        elif name in PACKAGE_PRICED_ITEMS:
            updates["pricing_method"] = "PACKAGE"
        else:
            if equipment.unit_price > 0:
                continue
            unit_price = equipment.price
            if name in CATEGORY_RATE_ITEMS:
                category_rule = _category_rule(PricingRule, equipment.category_id)
                if category_rule is not None and category_rule.unit_price > 0:
                    unit_price = category_rule.unit_price
            if unit_price <= 0:
                continue
            updates["pricing_method"] = "PER_UNIT"
            updates["unit_price"] = unit_price

        for field, value in updates.items():
            setattr(equipment, field, value)
        equipment.save(update_fields=list(updates))


def noop_reverse(apps, schema_editor):
    """The pre-migration state ("0.00" = not configured) is a valid config."""


class Migration(migrations.Migration):

    dependencies = [
        ("equipment", "0015_remove_equipment_equipment_price_nonnegative_and_more"),
        ("reservations", "0038_reservation_assigned_operator_and_more"),
    ]

    operations = [
        migrations.RunPython(sync_equipment_pricing, noop_reverse),
    ]
