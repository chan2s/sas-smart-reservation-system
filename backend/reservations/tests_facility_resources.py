"""Acceptance tests for facility-scoped resources/equipment.

Covers the facility -> resource relationship end to end:

* the facility resources endpoint returns ONLY the facility's own resources;
* changing facility changes the resource set;
* the backend rejects a resource that is not assigned to the selected facility;
* facility availability is capped by the facility's own inventory;
* the operator service fee is opt-in (and configurable per resource);
* overtime is charged at ₱300/hour beyond the 9 included hours.
"""

from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from equipment.models import Equipment, EquipmentCategory, FacilityResource
from facilities.models import Facility, OperatingHour
from .models import PricingRule, Reservation, ReservationItem
from .services.availability import check_availability
from .services.pricing import quote_fees

User = get_user_model()


class FacilityResourceTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.requester = User.objects.create_user(
            username="requester", password="pass12345", role=User.Role.REQUESTER
        )

        self.gym = Facility.objects.create(
            name="Gymnasium",
            facility_type=Facility.FacilityType.GYMNASIUM,
            capacity=2000,
        )
        self.avr = Facility.objects.create(
            name="Audio-Visual Room",
            facility_type=Facility.FacilityType.AVR,
            capacity=120,
        )

        # A near-future Monday so operating hours and dates never go stale.
        self.day = timezone.localdate() + timedelta(days=1)
        while self.day.weekday() != 0:
            self.day += timedelta(days=1)
        for facility in (self.gym, self.avr):
            OperatingHour.objects.create(
                facility=facility,
                day_of_week=self.day.weekday(),
                open_time=time(6, 0),
                close_time=time(22, 0),
            )

        self.sound_category = EquipmentCategory.objects.create(name="Sound Systems")
        self.projector_category = EquipmentCategory.objects.create(name="Projectors")
        self.chairs_category = EquipmentCategory.objects.create(name="Chairs")

        self.gym_sound = Equipment.objects.create(
            name="Portable Sound System",
            category=self.sound_category,
            total_quantity=4,
        )
        self.gym_chairs = Equipment.objects.create(
            name="Folding Chair", category=self.chairs_category, total_quantity=100
        )
        self.avr_projector = Equipment.objects.create(
            name="Portable Projector",
            category=self.projector_category,
            total_quantity=2,
        )

        # Facility-scoped assignments. The sound system is available to the
        # Gymnasium with an opt-in ₱500 operator service (and no per-unit fee).
        FacilityResource.objects.create(
            facility=self.gym,
            equipment=self.gym_sound,
            additional_fee="0.00",
            operator_available=True,
            operator_fee="500.00",
        )
        FacilityResource.objects.create(facility=self.gym, equipment=self.gym_chairs)
        FacilityResource.objects.create(
            facility=self.avr,
            equipment=self.avr_projector,
            operator_available=False,
        )

        # Deterministic facility/overtime rates (idempotent against the
        # default-rates data migration).
        PricingRule.objects.get_or_create(
            fee_type=PricingRule.FeeType.FACILITY,
            facility_type=Facility.FacilityType.GYMNASIUM,
            defaults={
                "label": "Gymnasium",
                "unit": PricingRule.Unit.FLAT,
                "unit_price": "5000.00",
                "included_hours": 9,
            },
        )
        PricingRule.objects.get_or_create(
            fee_type=PricingRule.FeeType.OVERTIME,
            facility_type=Facility.FacilityType.GYMNASIUM,
            defaults={
                "label": "Gymnasium Overtime",
                "unit": PricingRule.Unit.HOUR,
                "unit_price": "300.00",
                "included_hours": 9,
            },
        )

    # -- helpers ----------------------------------------------------------

    def _auth(self):
        self.client.force_authenticate(self.requester)

    def _payload(self, facility, items, **overrides):
        payload = {
            "facility_id": facility.id,
            "date": self.day.isoformat(),
            "start_time": "09:00",
            "end_time": "11:00",
            "event_name": "Orientation",
            "event_type": "ACADEMIC",
            "organization": "Student Affairs",
            "purpose": "Freshmen orientation",
            "expected_participants": 50,
            "items": items,
        }
        payload.update(overrides)
        return payload

    @staticmethod
    def _money(value):
        return f"{value:.2f}"

    # -- Test 1 / Test 2: facility filtering ------------------------------

    def test_facility_resources_endpoint_returns_only_that_facility(self):
        self._auth()
        response = self.client.get(f"/api/facilities/{self.gym.id}/resources/")
        self.assertEqual(response.status_code, 200, response.content)
        names = {row["name"] for row in response.json()["resources"]}
        self.assertEqual(names, {"Portable Sound System", "Folding Chair"})
        self.assertNotIn("Portable Projector", names)

    def test_changing_facility_replaces_resource_list(self):
        self._auth()
        gym = self.client.get(f"/api/facilities/{self.gym.id}/resources/").json()
        avr = self.client.get(f"/api/facilities/{self.avr.id}/resources/").json()
        gym_names = {row["name"] for row in gym["resources"]}
        avr_names = {row["name"] for row in avr["resources"]}
        self.assertIn("Portable Sound System", gym_names)
        self.assertNotIn("Portable Projector", gym_names)
        self.assertIn("Portable Projector", avr_names)
        self.assertNotIn("Portable Sound System", avr_names)

    def test_resource_exposes_operator_configuration(self):
        self._auth()
        response = self.client.get(f"/api/facilities/{self.gym.id}/resources/")
        sound = next(
            row
            for row in response.json()["resources"]
            if row["name"] == "Portable Sound System"
        )
        self.assertTrue(sound["operator_available"])
        self.assertFalse(sound["operator_required"])
        self.assertEqual(sound["operator_fee"], "500.00")

    # -- Test 3: backend rejects a foreign resource -----------------------

    def test_backend_rejects_resource_not_assigned_to_facility(self):
        self._auth()
        response = self.client.post(
            "/api/reservations/",
            self._payload(
                self.gym,
                [{"equipment_id": self.avr_projector.id, "quantity": 1}],
            ),
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("items", response.json())

    def test_backend_accepts_assigned_resource(self):
        self._auth()
        response = self.client.post(
            "/api/reservations/",
            self._payload(
                self.gym,
                [{"equipment_id": self.gym_chairs.id, "quantity": 10}],
            ),
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)

    # -- Test 4: availability / conflicts ---------------------------------

    def test_second_reservation_cannot_use_unavailable_resource(self):
        reservation = Reservation.objects.create(
            requester=self.requester,
            event_name="Blocked",
            facility=self.gym,
            date=self.day,
            start_time=time(9, 0),
            end_time=time(11, 0),
            status=Reservation.Status.APPROVED,
        )
        ReservationItem.objects.create(
            reservation=reservation, equipment=self.gym_sound, quantity=2
        )

        report = check_availability(
            self.gym.id,
            self.day,
            time(9, 0),
            time(11, 0),
            [{"equipment_id": self.gym_sound.id, "quantity": 3}],
        )
        self.assertFalse(report["overall"]["ok"])
        item = next(
            row for row in report["items"] if row["equipment_id"] == self.gym_sound.id
        )
        self.assertEqual(item["status"], "PARTIAL")

    def test_facility_availability_capped_by_assigned_quantity(self):
        resource = FacilityResource.objects.get(
            facility=self.gym, equipment=self.gym_sound
        )
        resource.quantity = 2
        resource.save(update_fields=["quantity"])
        report = check_availability(
            self.gym.id,
            self.day,
            time(9, 0),
            time(11, 0),
            [{"equipment_id": self.gym_sound.id, "quantity": 3}],
        )
        item = next(
            row for row in report["items"] if row["equipment_id"] == self.gym_sound.id
        )
        self.assertEqual(item["available"], 2)

    # -- Test 5 / 6: operator service -------------------------------------

    def test_operator_fee_added_when_requested(self):
        quote = quote_fees(
            Reservation.RequesterType.EXTERNAL,
            facility=self.gym,
            items=[
                {"equipment_id": self.gym_sound.id, "quantity": 1, "operator": True}
            ],
            start_time=time(13, 0),
            end_time=time(17, 0),
        )
        operator = next(
            line for line in quote["fees"] if line["fee_type"] == "OPERATOR"
        )
        self.assertEqual(self._money(operator["subtotal"]), "500.00")

    def test_no_operator_fee_when_not_requested(self):
        quote = quote_fees(
            Reservation.RequesterType.EXTERNAL,
            facility=self.gym,
            items=[
                {"equipment_id": self.gym_sound.id, "quantity": 1, "operator": False}
            ],
            start_time=time(13, 0),
            end_time=time(17, 0),
        )
        self.assertFalse(
            any(line["fee_type"] == "OPERATOR" for line in quote["fees"])
        )
        self.assertEqual(self._money(quote["total"]), "5000.00")

    def test_operator_required_forces_the_fee(self):
        resource = FacilityResource.objects.get(
            facility=self.gym, equipment=self.gym_sound
        )
        resource.operator_required = True
        resource.save(update_fields=["operator_required"])
        quote = quote_fees(
            Reservation.RequesterType.EXTERNAL,
            facility=self.gym,
            items=[
                {"equipment_id": self.gym_sound.id, "quantity": 1, "operator": False}
            ],
            start_time=time(13, 0),
            end_time=time(17, 0),
        )
        self.assertTrue(any(line["fee_type"] == "OPERATOR" for line in quote["fees"]))

    # -- Test 7: overtime -------------------------------------------------

    def test_overtime_plus_operator_total(self):
        quote = quote_fees(
            Reservation.RequesterType.EXTERNAL,
            facility=self.gym,
            items=[
                {"equipment_id": self.gym_sound.id, "quantity": 1, "operator": True}
            ],
            start_time=time(8, 0),
            end_time=time(19, 0),
        )
        # 9 included hours + 2 overtime hours = ₱5,000 + ₱600 + ₱500 operator.
        self.assertEqual(self._money(quote["total"]), "6100.00")
        overtime = next(
            line for line in quote["fees"] if line["fee_type"] == "OVERTIME"
        )
        self.assertEqual(self._money(overtime["quantity"]), "2.00")

    def test_internal_requester_never_charged_for_facility_resource(self):
        quote = quote_fees(
            Reservation.RequesterType.CAMPUS,
            facility=self.gym,
            items=[
                {"equipment_id": self.gym_sound.id, "quantity": 1, "operator": True}
            ],
            start_time=time(8, 0),
            end_time=time(19, 0),
        )
        self.assertFalse(quote["external"])
        self.assertEqual(quote["total"], 0)


class FacilityResourceRecommendationTests(TestCase):
    """Recommendations only suggest resources assigned to the facility."""

    def setUp(self):
        self.gym = Facility.objects.create(
            name="Gymnasium", facility_type=Facility.FacilityType.GYMNASIUM, capacity=500
        )
        self.avr = Facility.objects.create(
            name="Audio-Visual Room", facility_type=Facility.FacilityType.AVR, capacity=120
        )
        self.sound_category = EquipmentCategory.objects.create(name="Sound Systems")
        self.projector_category = EquipmentCategory.objects.create(name="Projectors")
        self.gym_sound = Equipment.objects.create(
            name="Gym Sound", category=self.sound_category, total_quantity=2
        )
        self.avr_projector = Equipment.objects.create(
            name="AVR Projector", category=self.projector_category, total_quantity=2
        )
        FacilityResource.objects.create(facility=self.gym, equipment=self.gym_sound)
        FacilityResource.objects.create(facility=self.avr, equipment=self.avr_projector)

    def test_only_facility_resources_are_recommended(self):
        from .services.recommendations import recommend_resources

        gym_recs = recommend_resources(
            "SEMINAR", 100, facility_id=self.gym.id
        )
        recommended_ids = {row["equipment_id"] for row in gym_recs}
        self.assertIn(self.gym_sound.id, recommended_ids)
        self.assertNotIn(self.avr_projector.id, recommended_ids)
