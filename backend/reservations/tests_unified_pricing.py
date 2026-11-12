from datetime import date, time
from decimal import Decimal

from django.test import TestCase

from equipment.models import Equipment, EquipmentCategory
from facilities.models import Facility
from reservations.models import PricingRule, Reservation, ReservationFee, ReservationItem
from reservations.services.pricing import quote_fees, snapshot_reservation_fees


class UnifiedRentalPricingTests(TestCase):
    def setUp(self):
        self.facility, _ = Facility.objects.get_or_create(
            name="Gymnasium", defaults={"facility_type": Facility.FacilityType.GYMNASIUM}
        )
        self.categories = {
            name: EquipmentCategory.objects.get_or_create(name=name)[0]
            for name in ("LED Wall", "Sound System", "Plastic Chairs")
        }
        self.items = {
            name: Equipment.objects.update_or_create(
                name=name,
                defaults={
                    "category": self.categories[name],
                    "unit": "piece" if name == "Plastic Chairs" else "unit",
                    "total_quantity": 100,
                    "is_active": True,
                },
            )[0]
            for name in self.categories
        }
        for period, price, unit in (
            ("WHOLE_DAY", "5000.00", PricingRule.Unit.FLAT),
            ("HALF_DAY", "2500.00", PricingRule.Unit.FLAT),
            ("PER_HOUR", "650.00", PricingRule.Unit.HOUR),
        ):
            PricingRule.objects.update_or_create(
                fee_type=PricingRule.FeeType.FACILITY,
                facility_type=Facility.FacilityType.GYMNASIUM,
                rental_period=period,
                equipment_category=None,
                defaults={"label": "Gymnasium", "unit": unit, "unit_price": Decimal(price), "is_active": True},
            )
        for name, period, price, unit in (
            ("LED Wall", "WHOLE_DAY", "15000.00", PricingRule.Unit.FLAT),
            ("LED Wall", "HALF_DAY", "7500.00", PricingRule.Unit.FLAT),
            ("Sound System", "", "1000.00", PricingRule.Unit.UNIT),
            ("Plastic Chairs", "", "5.00", PricingRule.Unit.UNIT),
        ):
            PricingRule.objects.update_or_create(
                fee_type=PricingRule.FeeType.EQUIPMENT,
                equipment_category=self.categories[name],
                rental_period=period,
                defaults={"label": name, "unit": unit, "unit_price": Decimal(price), "is_active": True},
            )
        for name in ("LED Wall", "Sound System"):
            PricingRule.objects.update_or_create(
                fee_type=PricingRule.FeeType.OPERATOR,
                equipment_category=self.categories[name],
                rental_period="",
                defaults={"label": f"{name} Operator", "unit": PricingRule.Unit.FLAT, "unit_price": Decimal("500.00"), "is_active": True},
            )
        PricingRule.objects.update_or_create(
            fee_type=PricingRule.FeeType.ENVIRONMENTAL,
            facility_type="",
            equipment_category=None,
            rental_period="",
            defaults={"label": "Environmental Fee", "unit": PricingRule.Unit.FLAT, "unit_price": Decimal("500.00"), "is_active": True},
        )

    def quote(self, requester_type, target_date, start, end):
        return quote_fees(
            requester_type,
            facility=self.facility,
            items=[
                {"equipment": self.items["LED Wall"], "quantity": 1},
                {"equipment": self.items["Sound System"], "quantity": 1},
                {"equipment": self.items["Plastic Chairs"], "quantity": 10},
            ],
            start_time=start,
            end_time=end,
            target_date=target_date,
        )

    def test_external_weekday_whole_day_uses_official_prices_and_no_operator(self):
        quote = self.quote(
            Reservation.RequesterType.EXTERNAL,
            date(2026, 11, 12),
            time(8),
            time(17),
        )
        self.assertEqual(quote["total"], Decimal("21550.00"))
        self.assertEqual(quote["reference_total"], Decimal("21550.00"))
        self.assertEqual(
            [line["rental_period"] for line in quote["fees"] if line["fee_type"] == "FACILITY"],
            ["WHOLE_DAY"],
        )
        self.assertEqual(sum(line["fee_type"] == "OPERATOR" for line in quote["fees"]), 0)
        self.assertEqual(sum(line["fee_type"] == "ENVIRONMENTAL" for line in quote["fees"]), 1)

    def test_external_weekend_half_day_adds_both_operator_fees(self):
        quote = self.quote(
            Reservation.RequesterType.EXTERNAL,
            date(2026, 11, 14),
            time(8),
            time(12),
        )
        self.assertEqual(quote["total"], Decimal("12550.00"))
        operator_fees = [line for line in quote["fees"] if line["fee_type"] == "OPERATOR"]
        self.assertEqual(len(operator_fees), 2)
        self.assertTrue(all(line["subtotal"] == Decimal("500.00") for line in operator_fees))

    def test_internal_uses_same_reference_quote_but_zero_total_and_no_fee_records(self):
        quote = self.quote(
            Reservation.RequesterType.CAMPUS,
            date(2026, 11, 14),
            time(16),
            time(20),
        )
        self.assertEqual(quote["reference_total"], Decimal("12550.00"))
        self.assertEqual(quote["total"], Decimal("0.00"))
        self.assertTrue(quote["fees"])
        self.assertTrue(all(line["waived"] for line in quote["fees"]))

        reservation = Reservation.objects.create(
            event_name="Internal event",
            facility=self.facility,
            date=date(2026, 11, 14),
            start_time=time(16),
            end_time=time(20),
            requester_type=Reservation.RequesterType.CAMPUS,
        )
        ReservationItem.objects.create(
            reservation=reservation, equipment=self.items["Plastic Chairs"], quantity=10
        )
        self.assertEqual(snapshot_reservation_fees(reservation), Decimal("0.00"))
        reservation.refresh_from_db()
        self.assertEqual(reservation.estimated_total, Decimal("0.00"))
        self.assertFalse(reservation.fees.exists())

    def test_external_snapshot_persists_the_backend_calculated_charge(self):
        reservation = Reservation.objects.create(
            event_name="External event",
            facility=self.facility,
            date=date(2026, 11, 12),
            start_time=time(8),
            end_time=time(17),
            requester_type=Reservation.RequesterType.EXTERNAL,
        )
        for name, quantity in (("LED Wall", 1), ("Sound System", 1), ("Plastic Chairs", 10)):
            ReservationItem.objects.create(
                reservation=reservation,
                equipment=self.items[name],
                quantity=quantity,
            )
        self.assertEqual(snapshot_reservation_fees(reservation), Decimal("21550.00"))
        reservation.refresh_from_db()
        self.assertEqual(reservation.estimated_total, Decimal("21550.00"))
        self.assertEqual(
            reservation.fees.filter(fee_type=ReservationFee.FeeType.ENVIRONMENTAL).count(),
            1,
        )

    def test_external_weekday_past_five_adds_operator_fees(self):
        quote = self.quote(
            Reservation.RequesterType.EXTERNAL,
            date(2026, 11, 12),
            time(16),
            time(18),
        )
        self.assertEqual(sum(line["fee_type"] == "OPERATOR" for line in quote["fees"]), 2)

    def test_no_unlisted_overtime_or_weekend_maintenance_charge_is_applied(self):
        PricingRule.objects.create(
            fee_type=PricingRule.FeeType.OVERTIME,
            facility_type=Facility.FacilityType.GYMNASIUM,
            label="Legacy overtime",
            unit=PricingRule.Unit.HOUR,
            unit_price=Decimal("300.00"),
        )
        quote = quote_fees(
            Reservation.RequesterType.EXTERNAL,
            facility=self.facility,
            items=[],
            start_time=time(8),
            end_time=time(18),
            target_date=date(2026, 11, 14),
        )
        self.assertEqual(quote["total"], Decimal("5500.00"))
        self.assertFalse(any(line["fee_type"] == PricingRule.FeeType.OVERTIME for line in quote["fees"]))
