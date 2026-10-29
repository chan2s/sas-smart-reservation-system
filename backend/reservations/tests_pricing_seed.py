"""Tests for the production-safe pricing seed command.

Covers the configured rates, idempotency, conflict reporting (a production
rate is never overwritten), dry-run mode, and that unrelated operational data
— stock, availability, reservations, and fee snapshots — is preserved.
"""

from datetime import date, time
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from equipment.models import Equipment, EquipmentCategory, FacilityResource
from facilities.models import Facility
from reservations.models import PricingRule, Reservation, ReservationFee
from reservations.services.pricing import quote_fees

User = get_user_model()
D = Decimal


def run_seed(*args):
    """Run the command and return its console output."""
    output = StringIO()
    call_command("seed_production_pricing", *args, stdout=output)
    return output.getvalue()


class ProductionPricingSeedTests(TestCase):
    def setUp(self):
        self.gym = Facility.objects.create(
            name="Gymnasium",
            facility_type=Facility.FacilityType.GYMNASIUM,
            capacity=2000,
        )
        self.cafeteria = Facility.objects.create(
            name="Cafeteria",
            facility_type=Facility.FacilityType.CAFETERIA,
            capacity=500,
        )
        self.avr = Facility.objects.create(
            name="Audio-Visual Room",
            facility_type=Facility.FacilityType.AVR,
            capacity=120,
        )
        self.chairs = EquipmentCategory.objects.create(name="Chairs")
        self.sound_category = EquipmentCategory.objects.create(name="Sound Systems")
        self.chair = Equipment.objects.create(
            name="Folding Chair",
            category=self.chairs,
            total_quantity=200,
            price=D("0.00"),
        )
        self.sound = Equipment.objects.create(
            name="Portable Sound System",
            category=self.sound_category,
            total_quantity=4,
            price=D("0.00"),
        )
        # Start from an unconfigured database so creation is observable.
        PricingRule.objects.all().delete()

    # -- configured values -------------------------------------------------

    def test_seed_configures_the_standard_rates(self):
        run_seed()

        for facility_type, expected in (
            (Facility.FacilityType.GYMNASIUM, D("5000.00")),
            (Facility.FacilityType.CAFETERIA, D("5000.00")),
        ):
            facility_rule = PricingRule.objects.get(
                fee_type=PricingRule.FeeType.FACILITY,
                facility_type=facility_type,
            )
            self.assertEqual(facility_rule.unit_price, expected)
            self.assertEqual(facility_rule.unit, PricingRule.Unit.FLAT)
            self.assertEqual(facility_rule.included_hours, D("9.00"))
            self.assertTrue(facility_rule.is_active)

            overtime = PricingRule.objects.get(
                fee_type=PricingRule.FeeType.OVERTIME,
                facility_type=facility_type,
            )
            self.assertEqual(overtime.unit_price, D("300.00"))
            self.assertEqual(overtime.unit, PricingRule.Unit.HOUR)
            self.assertTrue(overtime.is_active)

        chair_rule = PricingRule.objects.get(
            fee_type=PricingRule.FeeType.EQUIPMENT,
            equipment_category=self.chairs,
        )
        self.assertEqual(chair_rule.unit_price, D("5.00"))
        self.assertEqual(chair_rule.unit, PricingRule.Unit.UNIT)

        operator_rule = PricingRule.objects.get(
            fee_type=PricingRule.FeeType.OPERATOR,
            equipment_category=self.sound_category,
        )
        self.assertEqual(operator_rule.unit_price, D("500.00"))
        self.assertEqual(operator_rule.unit, PricingRule.Unit.FLAT)
        self.assertEqual(operator_rule.label, "Sound System Operator")

        self.chair.refresh_from_db()
        self.assertEqual(self.chair.price, D("5.00"))
        # Stock is never touched.
        self.assertEqual(self.chair.total_quantity, 200)

    def test_seed_does_not_price_facility_types_outside_the_standard_rates(self):
        run_seed()
        self.assertFalse(
            PricingRule.objects.filter(
                facility_type=Facility.FacilityType.AVR
            ).exists()
        )

    def test_seed_creates_exactly_one_row_per_rate(self):
        run_seed()

        self.assertEqual(
            PricingRule.objects.filter(fee_type=PricingRule.FeeType.FACILITY).count(), 2
        )
        self.assertEqual(
            PricingRule.objects.filter(fee_type=PricingRule.FeeType.OVERTIME).count(), 2
        )
        self.assertEqual(
            PricingRule.objects.filter(fee_type=PricingRule.FeeType.EQUIPMENT).count(), 1
        )
        self.assertEqual(
            PricingRule.objects.filter(fee_type=PricingRule.FeeType.OPERATOR).count(), 1
        )

    def test_seed_creates_the_rates_from_an_unconfigured_database(self):
        run_seed()

        self.assertEqual(PricingRule.objects.count(), 6)
        gym_rule = PricingRule.objects.get(
            fee_type=PricingRule.FeeType.FACILITY,
            facility_type=Facility.FacilityType.GYMNASIUM,
        )
        self.assertEqual(str(gym_rule.unit_price), "5000.00")
        self.assertEqual(gym_rule.label, "Gymnasium")

    # -- idempotency -------------------------------------------------------

    def test_running_twice_creates_no_duplicates_and_changes_nothing(self):
        first = run_seed()
        self.assertIn("CREATED", first)

        snapshot = {
            rule.pk: (rule.unit_price, rule.unit, rule.included_hours, rule.is_active)
            for rule in PricingRule.objects.all()
        }
        chair_price = Equipment.objects.get(pk=self.chair.pk).price

        second = run_seed()

        self.assertEqual(
            {
                rule.pk: (rule.unit_price, rule.unit, rule.included_hours, rule.is_active)
                for rule in PricingRule.objects.all()
            },
            snapshot,
        )
        self.assertEqual(Equipment.objects.get(pk=self.chair.pk).price, chair_price)
        self.assertEqual(PricingRule.objects.count(), 6)
        self.assertEqual(
            PricingRule.objects.filter(
                fee_type=PricingRule.FeeType.FACILITY,
                facility_type=Facility.FacilityType.GYMNASIUM,
            ).count(),
            1,
        )
        # Creation and update nowhere; everything is verified as already correct.
        self.assertNotIn("CONFLICT", second)
        self.assertIn("UNCHANGED", second)
        self.assertNotIn("CREATED", second)

    # -- conflict handling -------------------------------------------------

    def test_conflicting_folding_chair_price_is_flagged_not_overwritten(self):
        self.chair.price = D("20.00")
        self.chair.save(update_fields=["price"])

        with self.assertRaises(CommandError) as ctx:
            run_seed()

        self.chair.refresh_from_db()
        self.assertEqual(self.chair.price, D("20.00"))
        self.assertIn("conflict", str(ctx.exception).lower())

    def test_conflicting_facility_rate_is_flagged_not_overwritten(self):
        PricingRule.objects.create(
            fee_type=PricingRule.FeeType.FACILITY,
            facility_type=Facility.FacilityType.GYMNASIUM,
            label="Gymnasium",
            unit=PricingRule.Unit.FLAT,
            unit_price=D("4500.00"),
            included_hours=D("9.00"),
        )

        with self.assertRaises(CommandError):
            run_seed()

        gym_rules = PricingRule.objects.filter(
            fee_type=PricingRule.FeeType.FACILITY,
            facility_type=Facility.FacilityType.GYMNASIUM,
        )
        self.assertEqual(gym_rules.count(), 1)
        self.assertEqual(gym_rules.get().unit_price, D("4500.00"))

    def test_inactive_rate_is_reported_and_not_reactivated(self):
        rule = PricingRule.objects.create(
            fee_type=PricingRule.FeeType.FACILITY,
            facility_type=Facility.FacilityType.CAFETERIA,
            label="Cafeteria",
            unit=PricingRule.Unit.FLAT,
            unit_price=D("5000.00"),
            included_hours=D("9.00"),
            is_active=False,
        )

        with self.assertRaises(CommandError):
            run_seed()

        rule.refresh_from_db()
        self.assertFalse(rule.is_active)

    def test_operator_rate_conflict_is_flagged_not_overwritten(self):
        PricingRule.objects.create(
            fee_type=PricingRule.FeeType.OPERATOR,
            equipment_category=self.sound_category,
            label="Sound System Operator",
            unit=PricingRule.Unit.FLAT,
            unit_price=D("750.00"),
        )

        with self.assertRaises(CommandError):
            run_seed()

        operator = PricingRule.objects.get(
            fee_type=PricingRule.FeeType.OPERATOR,
            equipment_category=self.sound_category,
        )
        self.assertEqual(operator.unit_price, D("750.00"))

    def test_conflicting_facility_resource_operator_fee_is_not_overwritten(self):
        resource = FacilityResource.objects.create(
            facility=self.gym,
            equipment=self.sound,
            quantity=3,
            operator_available=True,
            operator_fee=D("750.00"),
        )

        with self.assertRaises(CommandError):
            run_seed()

        resource.refresh_from_db()
        self.assertEqual(resource.operator_fee, D("750.00"))
        self.assertEqual(resource.quantity, 3)

    # -- service fee on facility resources --------------------------------

    def test_operator_fee_is_configured_only_where_the_service_is_offered(self):
        offered = FacilityResource.objects.create(
            facility=self.gym,
            equipment=self.sound,
            quantity=2,
            additional_fee=D("0.00"),
            operator_available=True,
            operator_fee=D("0.00"),
        )
        not_offered = FacilityResource.objects.create(
            facility=self.cafeteria,
            equipment=self.sound,
            quantity=0,
            operator_available=False,
            operator_fee=D("0.00"),
        )

        run_seed()

        offered.refresh_from_db()
        not_offered.refresh_from_db()
        self.assertEqual(offered.operator_fee, D("500.00"))
        self.assertEqual(offered.quantity, 2)
        self.assertEqual(offered.additional_fee, D("0.00"))
        self.assertEqual(not_offered.operator_fee, D("0.00"))

    # -- dry run -----------------------------------------------------------

    def test_dry_run_reports_the_plan_and_writes_nothing(self):
        PricingRule.objects.all().delete()
        output = run_seed("--dry-run")

        self.assertEqual(PricingRule.objects.count(), 0)
        self.chair.refresh_from_db()
        self.assertEqual(self.chair.price, D("0.00"))
        self.assertIn("Dry run", output)
        self.assertIn("would create", output)
        self.assertIn("would set the price to PHP 5.00", output)

    # -- preservation ------------------------------------------------------

    def test_seed_preserves_unrelated_production_data(self):
        projectors = EquipmentCategory.objects.create(name="Projectors")
        projector = Equipment.objects.create(
            name="Portable Projector",
            category=projectors,
            total_quantity=5,
            price=D("250.00"),
        )
        projector_rule = PricingRule.objects.create(
            fee_type=PricingRule.FeeType.EQUIPMENT,
            equipment_category=projectors,
            label="Projectors",
            unit=PricingRule.Unit.UNIT,
            unit_price=D("250.00"),
        )
        self.cafeteria.is_active = False
        self.cafeteria.status = Facility.Status.MAINTENANCE
        self.cafeteria.save(update_fields=["is_active", "status"])

        requester = User.objects.create_user(username="campus", password="pass12345")
        reservation = Reservation.objects.create(
            requester=requester,
            event_name="Historical Event",
            facility=self.cafeteria,
            date=date(2026, 9, 1),
            start_time=time(8, 0),
            end_time=time(17, 0),
            status=Reservation.Status.COMPLETED,
            estimated_total=D("1234.56"),
        )
        fee = ReservationFee.objects.create(
            reservation=reservation,
            fee_type=ReservationFee.FeeType.FACILITY,
            description="Cafeteria",
            unit="flat",
            unit_price=D("1234.56"),
            subtotal=D("1234.56"),
        )

        run_seed()

        self.cafeteria.refresh_from_db()
        self.assertFalse(self.cafeteria.is_active)
        self.assertEqual(self.cafeteria.status, Facility.Status.MAINTENANCE)
        self.assertEqual(self.cafeteria.capacity, 500)

        projector.refresh_from_db()
        self.assertEqual(projector.total_quantity, 5)
        self.assertEqual(projector.price, D("250.00"))
        projector_rule.refresh_from_db()
        self.assertEqual(projector_rule.unit_price, D("250.00"))

        reservation.refresh_from_db()
        fee.refresh_from_db()
        self.assertEqual(reservation.estimated_total, D("1234.56"))
        self.assertEqual(fee.unit_price, D("1234.56"))
        self.assertEqual(fee.subtotal, D("1234.56"))
        self.assertEqual(Reservation.objects.count(), 1)
        self.assertEqual(ReservationFee.objects.count(), 1)
        self.assertEqual(User.objects.count(), 1)

    # -- the seeded rates drive the pricing engine ------------------------

    def test_seeded_rates_are_used_by_the_backend_quote(self):
        run_seed()

        def quote(facility, requester_type, start, end, items=None):
            return quote_fees(
                requester_type,
                facility=facility,
                items=items or [],
                start_time=start,
                end_time=end,
            )

        chairs = [{"equipment_id": self.chair.id, "quantity": 10}]
        internal = quote(
            self.gym, Reservation.RequesterType.CAMPUS, time(8, 0), time(17, 0), chairs
        )
        self.assertEqual(internal["fees"], [])
        self.assertEqual(internal["total"], 0)

        external = quote(
            self.gym, Reservation.RequesterType.EXTERNAL, time(8, 0), time(17, 0), chairs
        )
        self.assertEqual(external["total"], D("5050.00"))
        self.assertEqual(external["included_hours"], D("9.00"))
        self.assertEqual(external["overtime_hours"], D("0.00"))

        overtime = quote(
            self.gym, Reservation.RequesterType.EXTERNAL, time(8, 0), time(19, 0)
        )
        self.assertEqual(overtime["overtime_hours"], D("2.00"))
        self.assertEqual(overtime["total"], D("5600.00"))

        cafeteria = quote(
            self.cafeteria, Reservation.RequesterType.EXTERNAL, time(8, 0), time(17, 0)
        )
        self.assertEqual(cafeteria["total"], D("5000.00"))

        # A facility type without a configured rate stays free.
        avr = quote(self.avr, Reservation.RequesterType.EXTERNAL, time(8, 0), time(17, 0))
        self.assertEqual(avr["total"], D("0.00"))

        # Sound system operator: ₱500 flat service fee via the operator rule.
        operator = quote(
            self.gym,
            Reservation.RequesterType.EXTERNAL,
            time(8, 0),
            time(17, 0),
            [{"equipment_id": self.sound.id, "quantity": 1}],
        )
        operator_line = next(
            line
            for line in operator["fees"]
            if line["fee_type"] == PricingRule.FeeType.OPERATOR
        )
        self.assertEqual(operator_line["unit_price"], D("500.00"))
        self.assertEqual(operator_line["unit"], PricingRule.Unit.FLAT)
        self.assertEqual(operator["total"], D("5500.00"))


class SeedWithoutInventoryTests(TestCase):
    def test_missing_facilities_and_equipment_are_reported_not_created(self):
        output = run_seed()

        self.assertEqual(Facility.objects.count(), 0)
        self.assertEqual(Equipment.objects.count(), 0)
        self.assertEqual(EquipmentCategory.objects.count(), 0)
        self.assertIn("no equipment named 'Folding Chair'", output)
        self.assertIn("no 'Sound Systems' equipment category", output)
        # The rates that need no related rows are still configured.
        self.assertEqual(
            PricingRule.objects.filter(fee_type=PricingRule.FeeType.FACILITY).count(), 2
        )


class PreSeededPricingTests(TestCase):
    def test_existing_matching_rates_are_left_untouched(self):
        before = {
            rule.pk: (rule.unit_price, rule.unit, rule.included_hours, rule.is_active)
            for rule in PricingRule.objects.all()
        }
        self.assertTrue(before)

        output = run_seed()

        self.assertEqual(PricingRule.objects.count(), len(before))
        for rule in PricingRule.objects.all():
            self.assertEqual(
                (rule.unit_price, rule.unit, rule.included_hours, rule.is_active),
                before[rule.pk],
            )
        self.assertIn("UNCHANGED", output)
        self.assertNotIn("CONFLICT", output)
