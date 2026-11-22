"""Official rental configuration for the LED Wall and Sound System.

Covers the Edit Equipment modal's saved fields and the reservation pricing
service that consumes them: duration rates, the single package rate, and the
flat operator fee that applies only on weekends or after 5:00 PM on weekdays.
"""

from datetime import date, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from equipment.models import Equipment, FacilityResource
from facilities.models import Facility
from reservations.models import PricingRule, Reservation
from reservations.services.pricing import quote_fees

User = get_user_model()


class OfficialRentalConfigurationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="rental_admin", password="pass12345", role=User.Role.ADMIN
        )
        self.facility = Facility.objects.create(
            name="Rental Gymnasium",
            facility_type=Facility.FacilityType.GYMNASIUM,
            capacity=1000,
        )
        # The official catalog rows are created by the catalog migration.
        # LED Wall is now a single package, so the old 100-unit setup is
        # replaced with the corrected physical inventory (1 package).
        self.led = Equipment.objects.get(name="LED Wall")
        self.led.total_quantity = 1
        self.led.unit = Equipment.Unit.PACKAGE
        self.led.pricing_method = Equipment.PricingMethod.DURATION
        self.led.whole_day_price = Decimal("15000.00")
        self.led.half_day_price = Decimal("7000.00")
        self.led.hourly_rate = Decimal("0.00")
        self.led.operator_fee = Decimal("500.00")
        self.led.save()

        self.sound = Equipment.objects.get(name="Sound System")
        self.sound.total_quantity = 1
        self.sound.unit = Equipment.Unit.PACKAGE
        self.sound.pricing_method = Equipment.PricingMethod.PACKAGE
        self.sound.package_price = Decimal("1000.00")
        self.sound.operator_fee = Decimal("500.00")
        self.sound.save()

    def _quote(self, target_date, start, end, items=None):
        return quote_fees(
            Reservation.RequesterType.EXTERNAL,
            facility=self.facility,
            items=items
            or [{"equipment": self.led, "quantity": 1}, {"equipment": self.sound, "quantity": 1}],
            start_time=start,
            end_time=end,
            target_date=target_date,
        )

    @staticmethod
    def _lines(quote, fee_type):
        return [line for line in quote["fees"] if line["fee_type"] == fee_type]

    # -- saved configuration ------------------------------------------------

    def test_equipment_api_exposes_saved_led_wall_configuration(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(f"/api/equipment/{self.led.id}/")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["total_quantity"], 1)
        self.assertEqual(body["unit"], "package")
        self.assertEqual(body["whole_day_price"], "15000.00")
        self.assertEqual(body["half_day_price"], "7000.00")
        self.assertEqual(body["operator_fee"], "500.00")

    def test_equipment_api_exposes_saved_sound_system_package(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(f"/api/equipment/{self.sound.id}/")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["total_quantity"], 1)
        self.assertEqual(body["unit"], "package")
        self.assertEqual(body["pricing_method"], "PACKAGE")
        self.assertEqual(body["package_price"], "1000.00")
        self.assertEqual(body["operator_fee"], "500.00")

    def test_saving_and_reopening_preserves_the_modal_values(self):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            f"/api/equipment/{self.led.id}/",
            {
                "total_quantity": 1,
                "unit": "package",
                "pricing_method": "DURATION",
                "whole_day_price": "15000.00",
                "half_day_price": "7000.00",
                "operator_fee": "500.00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        reopened = self.client.get(f"/api/equipment/{self.led.id}/").json()
        self.assertEqual(reopened["whole_day_price"], "15000.00")
        self.assertEqual(reopened["half_day_price"], "7000.00")
        self.assertEqual(reopened["operator_fee"], "500.00")

    # -- reservation pricing -------------------------------------------------

    def test_led_wall_whole_and_half_day_rates(self):
        whole = self._quote(date(2026, 11, 12), time(8), time(17))
        half = self._quote(date(2026, 11, 12), time(8), time(12))
        whole_led = next(line for line in self._lines(whole, "EQUIPMENT") if line["equipment_id"] == self.led.id)
        half_led = next(line for line in self._lines(half, "EQUIPMENT") if line["equipment_id"] == self.led.id)
        self.assertEqual(whole_led["unit_price"], Decimal("15000.00"))
        self.assertEqual(half_led["unit_price"], Decimal("7000.00"))

    def test_weekday_booking_ending_at_five_has_no_operator_fee(self):
        quote = self._quote(date(2026, 11, 12), time(8), time(17))  # Thursday
        self.assertEqual(self._lines(quote, "OPERATOR"), [])

    def test_weekday_booking_past_five_adds_each_operator_fee_once(self):
        quote = self._quote(date(2026, 11, 12), time(8), time(17, 1))
        operator = self._lines(quote, "OPERATOR")
        self.assertEqual(len(operator), 2)
        self.assertEqual(
            sorted(line["subtotal"] for line in operator),
            [Decimal("500.00"), Decimal("500.00")],
        )

    def test_weekend_booking_adds_the_operator_fees(self):
        quote = self._quote(date(2026, 11, 14), time(8), time(10))  # Saturday
        operator = self._lines(quote, "OPERATOR")
        self.assertEqual(len(operator), 2)
        self.assertTrue(all(line["subtotal"] == Decimal("500.00") for line in operator))

    def test_package_rate_is_charged_once_not_per_component(self):
        FacilityResource.objects.create(facility=self.facility, equipment=self.sound)
        quote = self._quote(date(2026, 11, 12), time(8), time(17))
        sound_line = next(
            line for line in self._lines(quote, "EQUIPMENT") if line["equipment_id"] == self.sound.id
        )
        self.assertEqual(sound_line["quantity"], Decimal("1.00"))
        self.assertEqual(sound_line["unit_price"], Decimal("1000.00"))
        self.assertEqual(sound_line["subtotal"], Decimal("1000.00"))

    def test_assignment_with_zero_fee_uses_the_saved_operator_fee(self):
        """Official catalog assignments store no fee; the item configuration
        must still supply the operator fee, gated by the booking time."""
        FacilityResource.objects.create(
            facility=self.facility, equipment=self.sound, operator_fee=Decimal("0.00")
        )
        weekday = self._quote(date(2026, 11, 12), time(8), time(17))
        late = self._quote(date(2026, 11, 12), time(8), time(18))
        self.assertEqual(self._lines(weekday, "OPERATOR"), [])
        sound_operator = next(line for line in self._lines(late, "OPERATOR") if line["equipment_id"] == self.sound.id)
        self.assertEqual(sound_operator["subtotal"], Decimal("500.00"))

    def test_operator_fee_is_not_multiplied_by_reservation_duration(self):
        saturday = self._quote(date(2026, 11, 14), time(8), time(20))
        led_operator = next(
            line for line in self._lines(saturday, "OPERATOR") if line["equipment_id"] == self.led.id
        )
        self.assertEqual(led_operator["quantity"], Decimal("1.00"))
        self.assertEqual(led_operator["subtotal"], Decimal("500.00"))


class OfficialRentalConfigurationMigrationTests(TestCase):
    """The data migration leaves the catalog on the requested configuration
    without touching reservations or assignments."""

    def test_catalog_values_after_migrations(self):
        led = Equipment.objects.get(is_active=True, name__iexact="LED Wall")
        sound = Equipment.objects.get(is_active=True, name__iexact="Sound System")
        # LED Wall is a single package, not 100 individual units.
        self.assertEqual(led.total_quantity, 1)
        self.assertEqual(led.unit, "package")
        self.assertEqual(led.whole_day_price, Decimal("15000.00"))
        self.assertEqual(led.half_day_price, Decimal("7000.00"))
        self.assertEqual(led.operator_fee, Decimal("500.00"))
        self.assertEqual(sound.total_quantity, 1)
        self.assertEqual(sound.unit, "package")
        self.assertEqual(sound.pricing_method, Equipment.PricingMethod.PACKAGE)
        self.assertEqual(sound.operator_fee, Decimal("500.00"))
        # The package rate is copied from the existing rate; it is never
        # replaced with a newly invented amount.
        self.assertGreater(sound.package_price, 0)
