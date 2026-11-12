"""Seed the single NORSU-BSC official rental pricing configuration."""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from equipment.models import EquipmentCategory
from facilities.models import Facility
from reservations.models import PricingRule


class Command(BaseCommand):
    help = "Apply the official unified SAS RESERVE rental price table."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Preview without writing.")

    def handle(self, *args, **options):
        self.dry_run = bool(options["dry_run"])
        if self.dry_run:
            self.stdout.write(self.style.WARNING("Dry run: no records will be changed."))
            self._report_plan()
            return
        with transaction.atomic():
            categories = {}
            for name in ("LED Wall", "Sound System", "Plastic Chairs"):
                categories[name], _ = EquipmentCategory.objects.update_or_create(
                    name=name, defaults={"is_active": True}
                )

            # Obsolete overtime and all former pricing rows remain in the
            # database for audit, but cannot affect new quotes.
            PricingRule.objects.all().update(is_active=False)

            facility_rates = (
                ("WHOLE_DAY", "5000.00", PricingRule.Unit.FLAT),
                ("HALF_DAY", "2500.00", PricingRule.Unit.FLAT),
                ("PER_HOUR", "650.00", PricingRule.Unit.HOUR),
            )
            for facility_type, label in (
                (Facility.FacilityType.GYMNASIUM, "Gymnasium"),
                (Facility.FacilityType.CAFETERIA, "Dorm Cafeteria"),
            ):
                for period, price, unit in facility_rates:
                    self._save_rule(
                        fee_type=PricingRule.FeeType.FACILITY,
                        facility_type=facility_type,
                        equipment_category=None,
                        rental_period=period,
                        label=label,
                        unit=unit,
                        price=Decimal(price),
                    )

            for period, price in (("WHOLE_DAY", "15000.00"), ("HALF_DAY", "7500.00")):
                self._save_rule(
                    fee_type=PricingRule.FeeType.EQUIPMENT,
                    facility_type="",
                    equipment_category=categories["LED Wall"],
                    rental_period=period,
                    label="LED Wall",
                    unit=PricingRule.Unit.FLAT,
                    price=Decimal(price),
                )
            for name, price in (("Sound System", "1000.00"), ("Plastic Chairs", "5.00")):
                self._save_rule(
                    fee_type=PricingRule.FeeType.EQUIPMENT,
                    facility_type="",
                    equipment_category=categories[name],
                    rental_period="",
                    label=name,
                    unit=PricingRule.Unit.UNIT,
                    price=Decimal(price),
                )
            for name in ("LED Wall", "Sound System"):
                self._save_rule(
                    fee_type=PricingRule.FeeType.OPERATOR,
                    facility_type="",
                    equipment_category=categories[name],
                    rental_period="",
                    label=f"{name} Operator",
                    unit=PricingRule.Unit.FLAT,
                    price=Decimal("500.00"),
                )
            self._save_rule(
                fee_type=PricingRule.FeeType.ENVIRONMENTAL,
                facility_type="",
                equipment_category=None,
                rental_period="",
                label="Environmental Fee",
                unit=PricingRule.Unit.FLAT,
                price=Decimal("500.00"),
            )
        self.stdout.write(self.style.SUCCESS("Official catalog rates applied; historical reservation snapshots were preserved."))

    def _save_rule(self, *, fee_type, facility_type, equipment_category, rental_period, label, unit, price):
        PricingRule.objects.update_or_create(
            fee_type=fee_type,
            facility_type=facility_type,
            equipment_category=equipment_category,
            rental_period=rental_period,
            defaults={
                "label": label,
                "unit": unit,
                "unit_price": price,
                "included_hours": Decimal("0.00"),
                "is_active": True,
            },
        )

    def _report_plan(self):
        for name in ("Gymnasium", "Dorm Cafeteria"):
            for period, rate in (("Whole day", "5,000.00"), ("Half day", "2,500.00"), ("Per hour", "650.00")):
                self.stdout.write(f"  {name} — {period}: PHP {rate}")
        for name, rate in (("LED Wall whole day", "15,000.00"), ("LED Wall half day", "7,500.00"), ("Sound System", "1,000.00"), ("Plastic Chairs per piece", "5.00"), ("Environmental and applicable operator fee", "500.00 each")):
            self.stdout.write(f"  {name}: PHP {rate}")
