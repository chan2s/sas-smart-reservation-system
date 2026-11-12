from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("equipment", "0011_equipmentcategory_is_active"),
    ]

    operations = [
        migrations.AlterField(
            model_name="equipment",
            name="price",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="Legacy item price retained for historical records. Manage current rental rates in the unified pricing configuration.",
                max_digits=10,
            ),
        ),
    ]
