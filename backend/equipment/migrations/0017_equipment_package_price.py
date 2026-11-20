from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("equipment", "0016_sync_equipment_pricing_configuration"),
    ]

    operations = [
        migrations.AddField(
            model_name="equipment",
            name="package_price",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text=(
                    "Price per package when using package-based pricing "
                    "(e.g., Sound System Package)"
                ),
                max_digits=12,
            ),
        ),
        migrations.RemoveConstraint(
            model_name="equipment",
            name="equipment_prices_nonnegative",
        ),
        migrations.AddConstraint(
            model_name="equipment",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("unit_price__gte", 0),
                    ("half_day_price__gte", 0),
                    ("whole_day_price__gte", 0),
                    ("hourly_rate__gte", 0),
                    ("package_price__gte", 0),
                ),
                name="equipment_prices_nonnegative",
            ),
        ),
    ]
