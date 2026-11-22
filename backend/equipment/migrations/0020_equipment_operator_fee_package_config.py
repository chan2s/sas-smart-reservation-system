from decimal import Decimal

from django.db import migrations, models


def configure_official_rentals(apps, schema_editor):
    """Apply the official LED Wall and Sound System rental configuration.

    These are the two configurable catalog items, so the values are written to
    the equipment row that Equipment Management and the Edit Equipment modal
    read. Existing facility assignments, reservations, and fee snapshots are
    untouched.

    The Sound System is a single package: its package rate is preserved. When
    no rate is stored on the item yet, the active category rate (or the legacy
    item price) is copied over instead of inventing a new amount. Operator fees
    are flat per reservation and only charged for weekend bookings or weekday
    bookings ending after 5:00 PM.
    """
    Equipment = apps.get_model("equipment", "Equipment")
    PricingRule = apps.get_model("reservations", "PricingRule")

    Equipment.objects.filter(is_active=True, name__iexact="LED Wall").update(
        total_quantity=100,
        pricing_method="DURATION",
        whole_day_price=Decimal("15000.00"),
        half_day_price=Decimal("7000.00"),
        hourly_rate=Decimal("0.00"),
        operator_fee=Decimal("500.00"),
    )

    for sound in Equipment.objects.filter(
        is_active=True, name__iexact="Sound System"
    ).iterator():
        updates = {
            "total_quantity": 1,
            "unit": "package",
            "pricing_method": "PACKAGE",
            "operator_fee": Decimal("500.00"),
        }
        if sound.package_price <= 0:
            # Preserve the rate that was already being charged: the active
            # Sound System category rate, then the legacy item price.
            rule = (
                PricingRule.objects.filter(
                    is_active=True,
                    fee_type="EQUIPMENT",
                    equipment_category_id=sound.category_id,
                    unit_price__gt=0,
                )
                .order_by("id")
                .first()
            )
            preserved = rule.unit_price if rule is not None else sound.price
            if preserved and preserved > 0:
                updates["package_price"] = preserved
        Equipment.objects.filter(pk=sound.pk).update(**updates)


def noop_reverse(apps, schema_editor):
    """The previous pricing configuration remains a valid state."""


class Migration(migrations.Migration):

    dependencies = [
        ("equipment", "0019_seed_recommendation_config"),
        ("reservations", "0043_delete_recommendationrule"),
    ]

    operations = [
        migrations.AddField(
            model_name="equipment",
            name="operator_fee",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text=(
                    "Flat operator/service fee per reservation. Charged only for "
                    "weekend bookings or weekday bookings ending after 5:00 PM."
                ),
                max_digits=12,
            ),
        ),
        migrations.AlterField(
            model_name="equipment",
            name="unit",
            field=models.CharField(
                choices=[
                    ("unit", "Unit"),
                    ("piece", "Piece"),
                    ("set", "Set"),
                    ("pair", "Pair"),
                    ("box", "Box"),
                    ("package", "Package"),
                ],
                default="unit",
                max_length=40,
            ),
        ),
        migrations.RunPython(configure_official_rentals, noop_reverse),
    ]
