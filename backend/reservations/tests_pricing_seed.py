from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from equipment.models import EquipmentCategory
from facilities.models import Facility
from reservations.models import PricingRule


class UnifiedPricingSeedTests(TestCase):
    def run_seed(self, *args):
        output = StringIO()
        call_command("seed_production_pricing", *args, stdout=output)
        return output.getvalue()

    def test_seed_contains_only_official_pricing_rules_and_exact_values(self):
        PricingRule.objects.all().update(is_active=False)
        self.run_seed()

        facility_rates = PricingRule.objects.filter(
            is_active=True, fee_type=PricingRule.FeeType.FACILITY
        )
        self.assertEqual(facility_rates.count(), 6)
        expected = {
            "WHOLE_DAY": Decimal("5000.00"),
            "HALF_DAY": Decimal("2500.00"),
            "PER_HOUR": Decimal("650.00"),
        }
        for facility_type in (Facility.FacilityType.GYMNASIUM, Facility.FacilityType.CAFETERIA):
            for period, price in expected.items():
                rule = facility_rates.get(facility_type=facility_type, rental_period=period)
                self.assertEqual(rule.unit_price, price)

        led = EquipmentCategory.objects.get(name="LED Wall")
        self.assertEqual(
            PricingRule.objects.get(
                is_active=True, fee_type=PricingRule.FeeType.EQUIPMENT,
                equipment_category=led, rental_period="WHOLE_DAY",
            ).unit_price,
            Decimal("15000.00"),
        )
        sound = EquipmentCategory.objects.get(name="Sound System")
        self.assertEqual(
            PricingRule.objects.get(
                is_active=True, fee_type=PricingRule.FeeType.EQUIPMENT,
                equipment_category=sound,
            ).unit_price,
            Decimal("1000.00"),
        )
        chairs = EquipmentCategory.objects.get(name="Plastic Chairs")
        self.assertEqual(
            PricingRule.objects.get(
                is_active=True, fee_type=PricingRule.FeeType.EQUIPMENT,
                equipment_category=chairs,
            ).unit_price,
            Decimal("5.00"),
        )
        self.assertEqual(
            PricingRule.objects.get(is_active=True, fee_type=PricingRule.FeeType.ENVIRONMENTAL).unit_price,
            Decimal("500.00"),
        )
        self.assertFalse(PricingRule.objects.filter(is_active=True, fee_type=PricingRule.FeeType.OVERTIME).exists())

    def test_seed_disables_obsolete_rates_and_is_repeatable(self):
        obsolete = PricingRule.objects.create(
            fee_type=PricingRule.FeeType.OVERTIME,
            facility_type=Facility.FacilityType.GYMNASIUM,
            label="Old overtime",
            unit=PricingRule.Unit.HOUR,
            unit_price=Decimal("300.00"),
            is_active=True,
        )
        self.run_seed()
        self.run_seed()
        obsolete.refresh_from_db()
        self.assertFalse(obsolete.is_active)
        self.assertEqual(PricingRule.objects.filter(is_active=True).count(), 13)

    def test_dry_run_does_not_change_pricing_records(self):
        rule = PricingRule.objects.create(
            fee_type=PricingRule.FeeType.OVERTIME,
            facility_type=Facility.FacilityType.GYMNASIUM,
            label="Legacy rate",
            unit=PricingRule.Unit.HOUR,
            unit_price=Decimal("300.00"),
            is_active=True,
        )
        before = list(PricingRule.objects.values_list("id", "is_active", "unit_price"))
        output = self.run_seed("--dry-run")
        self.assertIn("Dry run", output)
        self.assertEqual(list(PricingRule.objects.values_list("id", "is_active", "unit_price")), before)
        rule.refresh_from_db()
        self.assertTrue(rule.is_active)
