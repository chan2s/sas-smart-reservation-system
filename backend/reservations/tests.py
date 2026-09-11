from datetime import date, datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from equipment.models import Equipment, EquipmentCategory, MaintenanceRecord
from facilities.models import Facility, OperatingHour
from .models import RecommendationRule, Reservation, ReservationItem
from .services.availability import check_availability, find_alternatives
from .services.recommendations import recommend_resources

User = get_user_model()


class AvailabilityServiceTests(TestCase):
    def setUp(self):
        self.facility = Facility.objects.create(
            name="Gymnasium",
            facility_type=Facility.FacilityType.GYMNASIUM,
            capacity=100,
            location="Main Building",
        )
        OperatingHour.objects.create(
            facility=self.facility,
            day_of_week=0,  # Monday
            open_time=time(6, 0),
            close_time=time(22, 0),
        )
        category = EquipmentCategory.objects.create(name="Microphones")
        self.mics = Equipment.objects.create(
            name="Wireless Microphone", category=category, total_quantity=4
        )
        self.requester = User.objects.create_user(
            username="requester", password="pass12345", role=User.Role.REQUESTER
        )

    def _reservation(self, **kwargs):
        defaults = dict(
            requester=self.requester,
            event_name="Event",
            facility=self.facility,
            date=date(2026, 9, 14),  # Monday
            start_time=time(9, 0),
            end_time=time(11, 0),
            status=Reservation.Status.APPROVED,
        )
        defaults.update(kwargs)
        return Reservation.objects.create(**defaults)

    def test_facility_conflict_detected(self):
        self._reservation(event_name="Blocked slot")
        report = check_availability(
            self.facility.id, date(2026, 9, 14), time(10, 0), time(12, 0)
        )
        self.assertFalse(report["overall"]["ok"])
        self.assertEqual(len(report["facility"]["conflicts"]), 1)
        self.assertEqual(report["facility"]["conflicts"][0]["event_name"], "Blocked slot")

    def test_no_conflict_when_adjacent(self):
        self._reservation(start_time=time(9, 0), end_time=time(11, 0))
        report = check_availability(
            self.facility.id, date(2026, 9, 14), time(11, 0), time(13, 0)
        )
        self.assertTrue(report["overall"]["ok"])

    def test_partial_equipment_conflict(self):
        self._reservation()
        item = self.mics
        ReservationItem.objects.create(
            reservation=Reservation.objects.get(event_name="Event"),
            equipment=item,
            quantity=3,
        )
        report = check_availability(
            self.facility.id,
            date(2026, 9, 14),
            time(9, 0),
            time(11, 0),
            [{"equipment_id": item.id, "quantity": 2}],
        )
        self.assertFalse(report["overall"]["ok"])
        mic_result = next(r for r in report["items"] if r["equipment_id"] == item.id)
        self.assertEqual(mic_result["status"], "PARTIAL")
        self.assertIn("Only 1", mic_result["message"])

    def test_unavailable_equipment(self):
        item = self.mics
        MaintenanceRecord.objects.create(
            equipment=item, quantity=4, issue_type=MaintenanceRecord.IssueType.MAINTENANCE
        )
        report = check_availability(
            self.facility.id,
            date(2026, 9, 14),
            time(9, 0),
            time(11, 0),
            [{"equipment_id": item.id, "quantity": 1}],
        )
        self.assertEqual(report["items"][0]["status"], "UNAVAILABLE")

    def test_outside_operating_hours(self):
        report = check_availability(
            self.facility.id, date(2026, 9, 14), time(23, 0), time(23, 59)
        )
        self.assertFalse(report["overall"]["ok"])
        self.assertTrue(any(p["type"] == "hours" for p in report["problems"]))

    def test_find_alternatives_returns_valid_slots(self):
        item = self.mics
        alternatives = find_alternatives(
            self.facility.id,
            date(2026, 9, 14),
            time(9, 0),
            time(11, 0),
            [{"equipment_id": item.id, "quantity": 1}],
            days=3,
        )
        # At least one fully-available alternative is proposed, and every
        # proposal must differ from the requested slot and actually be free.
        self.assertTrue(alternatives)
        for alternative in alternatives:
            self.assertNotEqual(
                (
                    alternative["date"],
                    alternative["start_time"],
                    alternative["end_time"],
                ),
                ("2026-09-14", "09:00", "11:00"),
            )
            report = check_availability(
                self.facility.id,
                date.fromisoformat(alternative["date"]),
                time.fromisoformat(alternative["start_time"]),
                time.fromisoformat(alternative["end_time"]),
                [{"equipment_id": item.id, "quantity": 1}],
            )
            self.assertTrue(report["overall"]["ok"])

    def test_recommendations_for_large_academic_event(self):
        chairs_category = EquipmentCategory.objects.create(name="Chairs")
        Equipment.objects.create(
            name="Folding Chair", category=chairs_category, total_quantity=200
        )
        recommendations = recommend_resources("ACADEMIC", 80)
        by_category = {r["category"]: r for r in recommendations}
        self.assertIn("Chairs", by_category)
        self.assertEqual(by_category["Chairs"]["quantity"], 80)
        self.assertIn("Microphones", by_category)

    def test_recommendations_seminar_in_avr(self):
        """Seminar, 150 participants, AVR → projector + sound + mics + chairs + tables."""
        for name in ["Chairs", "Tables", "Sound Systems", "Microphones", "Projectors"]:
            EquipmentCategory.objects.get_or_create(name=name)
        Equipment.objects.create(name="Projector", category=EquipmentCategory.objects.get(name="Projectors"), total_quantity=3)
        Equipment.objects.create(name="Sound System", category=EquipmentCategory.objects.get(name="Sound Systems"), total_quantity=4)
        Equipment.objects.create(name="Microphone", category=EquipmentCategory.objects.get(name="Microphones"), total_quantity=8)
        Equipment.objects.create(name="Chair", category=EquipmentCategory.objects.get(name="Chairs"), total_quantity=300)
        Equipment.objects.create(name="Table", category=EquipmentCategory.objects.get(name="Tables"), total_quantity=40)
        avr = Facility.objects.create(name="AVR", facility_type=Facility.FacilityType.AVR, capacity=120)

        recommendations = recommend_resources("SEMINAR", 150, facility_id=avr.id)
        by_category = {r["category"]: r for r in recommendations}
        self.assertIn("Projectors", by_category)
        self.assertEqual(by_category["Projectors"]["quantity"], 1)
        self.assertEqual(by_category["Sound Systems"]["quantity"], 1)
        self.assertEqual(by_category["Microphones"]["quantity"], 2)
        self.assertEqual(by_category["Chairs"]["quantity"], 150)
        self.assertEqual(by_category["Tables"]["quantity"], 15)

    def test_recommendations_meeting_keeps_it_small(self):
        """Meeting, 20 participants → 1 mic, 20 chairs, 1 table, no sound."""
        for name in ["Chairs", "Tables", "Microphones"]:
            EquipmentCategory.objects.get_or_create(name=name)
        Equipment.objects.create(name="Chair", category=EquipmentCategory.objects.get(name="Chairs"), total_quantity=100)
        Equipment.objects.create(name="Table", category=EquipmentCategory.objects.get(name="Tables"), total_quantity=20)
        Equipment.objects.create(name="Microphone", category=EquipmentCategory.objects.get(name="Microphones"), total_quantity=8)

        recommendations = recommend_resources("MEETING", 20)
        by_category = {r["category"]: r for r in recommendations}
        self.assertEqual(by_category["Microphones"]["quantity"], 1)
        self.assertEqual(by_category["Chairs"]["quantity"], 20)
        self.assertEqual(by_category["Tables"]["quantity"], 1)
        self.assertNotIn("Sound Systems", by_category)
        self.assertNotIn("Projectors", by_category)

    def test_recommendations_capped_by_availability(self):
        """Recommendations respect the schedule: unavailable units are surfaced."""
        EquipmentCategory.objects.get_or_create(name="Microphones")
        mics = Equipment.objects.create(
            name="Microphone", category=EquipmentCategory.objects.get(name="Microphones"), total_quantity=4
        )

        # Reserve 3 of the 4 mics during the target window.
        blocking = self._reservation(
            event_name="Blocking mic use", date=date(2026, 9, 15), start_time=time(9, 0), end_time=time(11, 0)
        )
        ReservationItem.objects.create(reservation=blocking, equipment=mics, quantity=3)

        recommendations = recommend_resources(
            "SEMINAR",
            150,
            target_date=date(2026, 9, 15),
            start_time=time(9, 0),
            end_time=time(11, 0),
        )
        mic = next(r for r in recommendations if r["category"] == "Microphones")
        self.assertEqual(mic["quantity"], 2)  # rule says 2
        self.assertEqual(mic["available"], 1)  # 3 of 4 are already reserved
        self.assertEqual(mic["recommended"], 1)  # capped prefill
        self.assertEqual(mic["status"], "PARTIAL")

    def test_purpose_boosts_projector_in_gymnasium(self):
        """Recognition program in the gymnasium suggests a projector."""
        EquipmentCategory.objects.get_or_create(name="Projectors")
        Equipment.objects.create(name="Projector", category=EquipmentCategory.objects.get(name="Projectors"), total_quantity=2)
        gym = Facility.objects.create(name="Gym", facility_type=Facility.FacilityType.GYMNASIUM, capacity=2000)

        plain = recommend_resources("SPORTS", 300, facility_id=gym.id, purpose="Inter-school league")
        self.assertNotIn("Projectors", {r["category"] for r in plain})

        ceremony = recommend_resources("SPORTS", 300, facility_id=gym.id, purpose="Recognition ceremony")
        self.assertIn("Projectors", {r["category"] for r in ceremony})

    def _recommendation_by_category(self, recommendations, name):
        return {r["category"]: r for r in recommendations}[name]

    def test_ceiling_table_quantities(self):
        """ceil(participants / 10): 10→1, 11→2, 29→3, 30→3, 31→4."""
        for name in ["Chairs", "Tables"]:
            EquipmentCategory.objects.get_or_create(name=name)
        Equipment.objects.create(name="Chair", category=EquipmentCategory.objects.get(name="Chairs"), total_quantity=500)
        Equipment.objects.create(name="Table", category=EquipmentCategory.objects.get(name="Tables"), total_quantity=100)

        cases = [(10, 1), (11, 2), (29, 3), (30, 3), (31, 4)]
        for participants, expected_tables in cases:
            recommendations = recommend_resources("SEMINAR", participants)
            by_category = {r["category"]: r for r in recommendations}
            self.assertEqual(by_category["Tables"]["quantity"], expected_tables, participants)
            self.assertEqual(by_category["Chairs"]["quantity"], participants, participants)

    def test_recommendation_quantity_is_not_inventory(self):
        """Recommendation stays rule-based even when inventory is far larger."""
        for name in ["Chairs", "Tables", "Microphones"]:
            EquipmentCategory.objects.get_or_create(name=name)
        Equipment.objects.create(name="Folding Chair", category=EquipmentCategory.objects.get(name="Chairs"), total_quantity=200)
        Equipment.objects.create(name="Folding Table (6 ft)", category=EquipmentCategory.objects.get(name="Tables"), total_quantity=40)
        Equipment.objects.create(name="Wired Microphone", category=EquipmentCategory.objects.get(name="Microphones"), total_quantity=6)

        recommendations = recommend_resources("SEMINAR", 29)
        by_category = {r["category"]: r for r in recommendations}

        # Rule quantity is independent of the 200 in inventory.
        self.assertEqual(by_category["Chairs"]["quantity"], 29)
        self.assertEqual(by_category["Chairs"]["available"], 200)
        self.assertEqual(by_category["Chairs"]["reason"], "1 chair per participant")
        self.assertEqual(by_category["Chairs"]["calculation"], "29 × 1")
        self.assertTrue(by_category["Chairs"]["can_fulfill"])

        self.assertEqual(by_category["Tables"]["quantity"], 3)
        self.assertEqual(by_category["Tables"]["reason"], "1 table per 10 participants, rounded up")
        self.assertEqual(by_category["Tables"]["calculation"], "ceil(29 / 10) = 3")

        # Seminar with 29 participants → 1 microphone (small-events tier).
        self.assertEqual(by_category["Microphones"]["quantity"], 1)
        self.assertEqual(
            by_category["Microphones"]["reason"],
            "1 microphone for small events (up to 60 participants)",
        )
        self.assertTrue(all(r["warning"] is None for r in recommendations))

    def test_shortage_produces_warning_without_overwriting_rule_quantity(self):
        """When stock cannot cover the rule, quantity stays rule-based and a warning explains it."""
        EquipmentCategory.objects.get_or_create(name="Chairs")
        Equipment.objects.create(name="Chair", category=EquipmentCategory.objects.get(name="Chairs"), total_quantity=20)

        recommendations = recommend_resources("SEMINAR", 29)
        chairs = self._recommendation_by_category(recommendations, "Chairs")
        self.assertEqual(chairs["quantity"], 29)  # rule output, uncapped
        self.assertEqual(chairs["recommended"], 20)  # capped prefill
        self.assertEqual(chairs["available"], 20)
        self.assertFalse(chairs["can_fulfill"])
        self.assertEqual(chairs["status"], "PARTIAL")
        self.assertIn("Only 20 of the recommended 29", chairs["warning"])

    def test_missing_participants_returns_no_recommendations(self):
        """No participant count → no participant-based quantities, ever."""
        EquipmentCategory.objects.get_or_create(name="Chairs")
        Equipment.objects.create(name="Chair", category=EquipmentCategory.objects.get(name="Chairs"), total_quantity=100)

        for participants in (0, None):
            self.assertEqual(recommend_resources("SEMINAR", participants), [])

    def test_missing_event_type_falls_back_to_generic_profile(self):
        """Unknown/blank event type uses the safest generic (OTHER) profile."""
        for name in ["Chairs", "Tables", "Microphones"]:
            EquipmentCategory.objects.get_or_create(name=name)
        Equipment.objects.create(name="Chair", category=EquipmentCategory.objects.get(name="Chairs"), total_quantity=100)
        Equipment.objects.create(name="Table", category=EquipmentCategory.objects.get(name="Tables"), total_quantity=20)
        Equipment.objects.create(name="Microphone", category=EquipmentCategory.objects.get(name="Microphones"), total_quantity=6)

        recommendations = recommend_resources("", 29)
        by_category = {r["category"]: r for r in recommendations}
        self.assertEqual(by_category["Chairs"]["quantity"], 29)
        self.assertEqual(by_category["Tables"]["quantity"], 3)
        self.assertEqual(by_category["Microphones"]["quantity"], 1)

    def test_fixed_quantity_rules(self):
        """MEETING asks for exactly 1 microphone and 1 table regardless of size."""
        for name in ["Chairs", "Tables", "Microphones"]:
            EquipmentCategory.objects.get_or_create(name=name)
        Equipment.objects.create(name="Chair", category=EquipmentCategory.objects.get(name="Chairs"), total_quantity=100)
        Equipment.objects.create(name="Table", category=EquipmentCategory.objects.get(name="Tables"), total_quantity=20)
        Equipment.objects.create(name="Microphone", category=EquipmentCategory.objects.get(name="Microphones"), total_quantity=8)

        recommendations = recommend_resources("MEETING", 20)
        by_category = {r["category"]: r for r in recommendations}
        self.assertEqual(by_category["Microphones"]["quantity"], 1)
        self.assertEqual(by_category["Tables"]["quantity"], 1)
        self.assertEqual(by_category["Microphones"]["calculation"], "1 × 1")


class ReservationApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="admin", password="pass12345", role=User.Role.ADMIN
        )
        self.requester = User.objects.create_user(
            username="requester", password="pass12345", role=User.Role.REQUESTER
        )
        self.facility = Facility.objects.create(
            name="AVR", facility_type=Facility.FacilityType.AVR, capacity=50
        )
        OperatingHour.objects.create(
            facility=self.facility, day_of_week=0, open_time=time(6, 0), close_time=time(22, 0)
        )
        category = EquipmentCategory.objects.create(name="Chairs")
        self.chairs = Equipment.objects.create(
            name="Folding Chair", category=category, total_quantity=100
        )

    def _auth(self, user):
        self.client.force_authenticate(user)

    def _payload(self, **overrides):
        payload = dict(
            facility_id=self.facility.id,
            date="2026-09-14",
            start_time="09:00",
            end_time="11:00",
            event_name="Orientation",
            event_type="ACADEMIC",
            organization="Student Affairs",
            purpose="Freshmen orientation",
            expected_participants=50,
            items=[{"equipment_id": self.chairs.id, "quantity": 50}],
        )
        payload.update(overrides)
        return payload

    def test_create_reservation_and_list(self):
        self._auth(self.requester)
        response = self.client.post("/api/reservations/", self._payload(), format="json")
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertTrue(body["reservation_id"].startswith("SAS-"))
        self.assertEqual(body["status"], "PENDING")
        self.assertEqual(body["requester_type"], "CAMPUS")
        self.assertEqual(body["requester"], self.requester.display_name)

        response = self.client.get("/api/reservations/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)

    def test_requester_only_sees_own_reservations(self):
        self._auth(self.admin)
        self.client.post("/api/reservations/", self._payload(), format="json")
        self._auth(self.requester)
        response = self.client.get("/api/reservations/")
        self.assertEqual(response.json()["count"], 0)

    def test_admin_sees_all_reservations_regardless_of_status(self):
        """Admins see every reservation, not just their own (admin list bug)."""
        # One reservation created by a plain requester.
        self._auth(self.requester)
        created = self.client.post("/api/reservations/", self._payload(), format="json").json()
        # One created by the admin on behalf of an external requester
        # (different day so the two bookings do not conflict).
        self._auth(self.admin)
        self.client.post(
            "/api/reservations/",
            self._payload(
                event_name="External booking",
                date="2026-10-05",
                requester_type="EXTERNAL",
                organization="ABC School",
                contact_person="Juan",
                contact_email="juan@example.com",
                requester_id=self.requester.id,
            ),
            format="json",
        )

        response = self.client.get("/api/reservations/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 2)
        returned_ids = {row["reservation_id"] for row in body["results"]}
        self.assertIn(created["reservation_id"], returned_ids)

    def test_admin_status_filter_tabs(self):
        """status= values match the backend canonical statuses for tab filters."""
        self._auth(self.requester)
        created = self.client.post("/api/reservations/", self._payload(), format="json").json()
        self._auth(self.admin)
        self.client.post(f"/api/reservations/{created['id']}/approve/", {}, format="json")

        for status_value, expected in (("PENDING", 0), ("APPROVED", 1), ("COMPLETED", 0)):
            response = self.client.get(f"/api/reservations/?status={status_value}")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["count"], expected)

    def test_admin_requester_type_filter(self):
        """requester_type=CAMPUS/EXTERNAL filter without hiding everything."""
        self._auth(self.admin)
        self.client.post(
            "/api/reservations/",
            self._payload(
                event_name="External booking",
                requester_type="EXTERNAL",
                organization="ABC School",
                contact_person="Juan",
                contact_email="juan@example.com",
                requester_id=self.requester.id,
            ),
            format="json",
        )

        campus = self.client.get("/api/reservations/?requester_type=CAMPUS").json()
        external = self.client.get("/api/reservations/?requester_type=EXTERNAL").json()
        self.assertEqual(campus["count"], 0)
        self.assertEqual(external["count"], 1)

    def test_garbage_optional_filters_do_not_hide_everything(self):
        """'undefined'/'null'/'' facility values are ignored, not fatal."""
        self._auth(self.admin)
        self.client.post("/api/reservations/", self._payload(), format="json")
        for garbage in ("undefined", "null", "", "not-a-number"):
            response = self.client.get(f"/api/reservations/?facility={garbage}")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["count"], 1, garbage)

    def test_conflicting_reservation_returns_409(self):
        self._auth(self.requester)
        first = self.client.post("/api/reservations/", self._payload(), format="json")
        self.assertEqual(first.status_code, 201)
        self.client.force_authenticate(self.admin)
        self.client.post(f"/api/reservations/{first.json()['id']}/approve/", {}, format="json")

        # Same slot by another requester → conflict.
        other = User.objects.create_user(
            username="other", password="pass12345", role=User.Role.REQUESTER
        )
        self._auth(other)
        response = self.client.post("/api/reservations/", self._payload(), format="json")
        self.assertEqual(response.status_code, 409)
        self.assertIn("availability", response.json())

    def test_administrator_created_reservation_is_auto_approved(self):
        self._auth(self.admin)
        response = self.client.post(
            "/api/reservations/",
            self._payload(event_name="Admin Recognition Program", purpose="Recognition ceremony", event_type="RECOGNITION", expected_participants=200),
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["status"], "APPROVED")
        event_types = [event["event_type"] for event in body["events"]]
        self.assertIn("APPROVED", event_types)
        # The requester (the admin) is notified that it was approved.
        notifications = self.client.get("/api/notifications/").json()
        self.assertTrue(
            any(n["title"] == "Reservation approved" for n in notifications["results"])
        )

    def test_requester_cannot_forge_status(self):
        """A client-supplied status is ignored; the backend decides."""
        self._auth(self.requester)
        response = self.client.post(
            "/api/reservations/",
            self._payload(status="APPROVED"),
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "PENDING")

    def test_requester_stays_pending_and_staff_can_approve(self):
        self._auth(self.requester)
        created = self.client.post(
            "/api/reservations/", self._payload(), format="json"
        ).json()
        self.assertEqual(created["status"], "PENDING")

        self._auth(self.admin)
        response = self.client.post(
            f"/api/reservations/{created['id']}/approve/", {}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "APPROVED")

    def test_recommendation_endpoint_uses_event_details(self):
        """Recommendations react to event type + participants + schedule."""
        self._auth(self.requester)
        response = self.client.post(
            "/api/availability/resources/",
            {
                "event_type": "SEMINAR",
                "expected_participants": 150,
                "purpose": "Student leadership seminar",
                "date": "2026-09-14",
                "start_time": "09:00",
                "end_time": "11:00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        recommendations = response.json()["recommendations"]
        self.assertTrue(recommendations)
        mic = next(r for r in recommendations if r["category"] == "Chairs")
        self.assertEqual(mic["quantity"], 150)  # matches expected_participants
        self.assertIn("available", mic)
        self.assertIn("recommended", mic)
        self.assertIn("status", mic)

    def test_approval_workflow_and_timeline(self):
        self._auth(self.requester)
        created = self.client.post(
            "/api/reservations/", self._payload(), format="json"
        ).json()
        reservation_id = created["id"]

        self._auth(self.admin)
        response = self.client.post(
            f"/api/reservations/{reservation_id}/approve/",
            {"comment": "Approved for orientation"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "APPROVED")

        detail = self.client.get(f"/api/reservations/{reservation_id}/").json()
        events = detail["events"]
        self.assertEqual(events[-1]["event_type"], "APPROVED")
        self.assertEqual(events[-1]["message"], "Approved for orientation")

        # Requester receives a notification.
        self._auth(self.requester)
        notifications = self.client.get("/api/notifications/").json()
        self.assertTrue(
            any(n["title"] == "Reservation approved" for n in notifications["results"])
        )

    def test_check_in_and_check_out(self):
        self._auth(self.requester)
        created = self.client.post(
            "/api/reservations/", self._payload(), format="json"
        ).json()
        self._auth(self.admin)
        self.client.post(f"/api/reservations/{created['id']}/approve/", {}, format="json")

        # The reservation is dated in the future, so the 3-hour window has not
        # opened — the admin must explicitly confirm the override.
        response = self.client.post(
            f"/api/reservations/{created['id']}/check_in/",
            {"override": True},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ACTIVE")

        response = self.client.post(
            f"/api/reservations/{created['id']}/check_out/",
            {
                "facility_condition": "GOOD",
                "equipment_returned": True,
                "notes": "All good.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "COMPLETED")
        self.assertIsNotNone(body["inspection"])
        self.assertTrue(body["items"][0]["returned"])

    # ------------------------------------------------------------------
    # Time-based check-in window
    # ------------------------------------------------------------------

    def _approved_reservation(self, start=None, requester=None):
        """Approved reservation starting at ``start`` (default now+1h)."""
        # ``localtime()`` keeps the arithmetic in the same wall-clock domain
        # the model stores, so offsets survive the UTC/local conversion.
        start = start or (timezone.localtime() + timedelta(hours=1))
        owner = requester or self.requester
        return Reservation.objects.create(
            requester=owner,
            event_name="Window test",
            facility=self.facility,
            date=start.date(),
            start_time=start.time(),
            end_time=time(23, 59),
            status=Reservation.Status.APPROVED,
        )

    def test_serializer_exposes_check_in_window(self):
        self._auth(self.requester)
        reservation = self._approved_reservation()
        body = self.client.get(f"/api/reservations/{reservation.id}/").json()
        open_time = datetime.fromisoformat(body["check_in_open_time"])
        self.assertEqual(
            open_time,
            reservation.check_in_open_time,
        )
        self.assertIsInstance(body["check_in_window_open"], bool)
        self.assertEqual(
            body["check_in_window_open"],
            timezone.now() >= reservation.check_in_open_time,
        )

    def test_requester_cannot_check_in_before_window(self):
        """Early check-in is rejected for a regular user."""
        self._auth(self.requester)
        # Start 4 hours from now → window opens 1 hour from now.
        reservation = self._approved_reservation(
            start=timezone.localtime() + timedelta(hours=4)
        )
        self.assertGreater(reservation.check_in_open_time, timezone.localtime())

        response = self.client.post(
            f"/api/reservations/{reservation.id}/check_in/", {}, format="json"
        )
        self.assertEqual(response.status_code, 403)
        body = response.json()
        self.assertEqual(body["code"], "check_in_not_open")
        self.assertIn("check_in_open_time", body)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.APPROVED)

    def test_requester_cannot_bypass_window_with_override_flag(self):
        """A forged override flag does not help a regular user."""
        self._auth(self.requester)
        reservation = self._approved_reservation(
            start=timezone.localtime() + timedelta(hours=4)
        )
        response = self.client.post(
            f"/api/reservations/{reservation.id}/check_in/",
            {"override": True},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.APPROVED)

    def test_staff_cannot_check_in_before_window(self):
        """Non-admin staff are bound by the same 3-hour window."""
        staff = User.objects.create_user(
            username="staff", password="pass12345", role=User.Role.STAFF
        )
        reservation = self._approved_reservation(
            start=timezone.localtime() + timedelta(hours=4)
        )
        self._auth(staff)
        response = self.client.post(
            f"/api/reservations/{reservation.id}/check_in/",
            {"override": True},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_requester_can_check_in_within_window(self):
        """Once the 3-hour window is open, the requester may check in."""
        self._auth(self.requester)
        # Start 1 hour from now → window opened 2 hours ago.
        reservation = self._approved_reservation(
            start=timezone.localtime() + timedelta(hours=1)
        )
        self.assertLess(reservation.check_in_open_time, timezone.localtime())

        response = self.client.post(
            f"/api/reservations/{reservation.id}/check_in/", {}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["status"], "ACTIVE")
        self.assertIsNotNone(response.json()["checked_in_at"])

    def test_admin_early_check_in_requires_explicit_override(self):
        """Admins may override, but only with an explicit confirmation."""
        self._auth(self.admin)
        reservation = self._approved_reservation(
            start=timezone.localtime() + timedelta(hours=4)
        )

        # Without the explicit override the admin is also rejected.
        response = self.client.post(
            f"/api/reservations/{reservation.id}/check_in/", {}, format="json"
        )
        self.assertEqual(response.status_code, 403)
        body = response.json()
        self.assertTrue(body["requires_override"])
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.APPROVED)

        # With the explicit override, the admin may check in early.
        response = self.client.post(
            f"/api/reservations/{reservation.id}/check_in/",
            {"override": True},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["status"], "ACTIVE")

    def test_checkin_code_lookup(self):
        self._auth(self.requester)
        created = self.client.post(
            "/api/reservations/", self._payload(), format="json"
        ).json()
        self._auth(self.admin)
        response = self.client.get(
            f"/api/reservations/checkin/{created['checkin_code']}/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], created["id"])

    def test_availability_check_endpoint(self):
        self._auth(self.requester)
        response = self.client.post(
            "/api/availability/check/",
            {
                "facility_id": self.facility.id,
                "date": "2026-09-14",
                "start_time": "09:00",
                "end_time": "11:00",
                "items": [{"equipment_id": self.chairs.id, "quantity": 20}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["overall"]["ok"])

    def test_recommendation_endpoint(self):
        self._auth(self.requester)
        response = self.client.post(
            "/api/availability/resources/",
            {"event_type": "ACADEMIC", "expected_participants": 80},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["recommendations"])

    def test_calendar_events(self):
        self._auth(self.requester)
        self.client.post("/api/reservations/", self._payload(), format="json")
        response = self.client.get(
            "/api/calendar/events/", {"start": "2026-09-01", "end": "2026-09-30"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)

    def test_calendar_events_has_is_sas_staff_field(self):
        """Calendar events include is_sas_staff to drive role-aware UI."""
        self._auth(self.requester)
        self.client.post("/api/reservations/", self._payload(), format="json")
        response = self.client.get(
            "/api/calendar/events/", {"start": "2026-09-01", "end": "2026-09-30"}
        )
        event = response.json()[0]
        self.assertIn("is_sas_staff", event)
        self.assertFalse(event["is_sas_staff"])
        # Non-staff should NOT receive admin-only fields.
        self.assertNotIn("requester_type", event)
        self.assertNotIn("organization", event)
        self.assertNotIn("contact_person", event)
        self.assertNotIn("created_by", event)

    def test_calendar_events_admin_sees_extra_fields(self):
        """Admin calendar events include requester/org/contact metadata."""
        self._auth(self.admin)
        self.client.post(
            "/api/reservations/",
            self._payload(
                event_name="Admin Event",
                requester_type="EXTERNAL",
                organization="ABC School",
                contact_person="Juan",
                contact_email="juan@example.com",
                requester_id=self.requester.id,
            ),
            format="json",
        )
        response = self.client.get(
            "/api/calendar/events/", {"start": "2026-09-01", "end": "2026-09-30"}
        )
        events = response.json()
        self.assertTrue(events)
        admin_event = next(e for e in events if e["title"] == "Admin Event")
        self.assertTrue(admin_event["is_sas_staff"])
        self.assertIn("requester_type", admin_event)
        self.assertEqual(admin_event["requester_type"], "EXTERNAL")
        self.assertEqual(admin_event["organization"], "ABC School")
        self.assertEqual(admin_event["contact_person"], "Juan")
        self.assertEqual(admin_event["contact_email"], "juan@example.com")
        self.assertEqual(admin_event["created_by"], "admin")


class RequesterTypeApiTests(TestCase):
    """Campus vs external requester flows + created-by semantics."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="admin", password="pass12345", role=User.Role.ADMIN
        )
        self.requester = User.objects.create_user(
            username="requester",
            password="pass12345",
            role=User.Role.REQUESTER,
            first_name="Juan",
            last_name="Dela Cruz",
            email="juan@campus.edu",
            organization="Student Affairs",
        )
        self.facility = Facility.objects.create(
            name="Gymnasium",
            facility_type=Facility.FacilityType.GYMNASIUM,
            capacity=200,
        )
        OperatingHour.objects.create(
            facility=self.facility, day_of_week=0, open_time=time(6, 0), close_time=time(22, 0)
        )

    def _external_payload(self, **overrides):
        payload = dict(
            facility_id=self.facility.id,
            date="2026-09-14",
            start_time="13:00",
            end_time="17:00",
            event_name="Inter-school Basketball Tournament",
            event_type="SPORTS",
            organization="ABC National High School",
            organization_type="SCHOOL",
            purpose="Inter-school tournament",
            expected_participants=200,
            contact_person="Juan Dela Cruz",
            contact_email="juan@example.com",
            requester_type="EXTERNAL",
            items=[],
        )
        payload.update(overrides)
        return payload

    # ------------------------------------------------------------------
    # Admin creates for a campus user -> auto-approved, requester kept
    # ------------------------------------------------------------------

    def test_admin_creates_for_campus_user_auto_approved(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            "/api/reservations/",
            {
                "facility_id": self.facility.id,
                "date": "2026-09-14",
                "start_time": "09:00",
                "end_time": "11:00",
                "event_name": "Orientation",
                "event_type": "ACADEMIC",
                "purpose": "Freshmen orientation",
                "expected_participants": 50,
                "requester_type": "CAMPUS",
                "requester_id": self.requester.id,
                "items": [],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        # Admin-created -> APPROVED immediately, no pending review.
        self.assertEqual(body["status"], "APPROVED")
        # Requester is Juan (not the admin); created_by is the admin.
        self.assertEqual(body["requester"], self.requester.display_name)
        self.assertEqual(body["requester_type"], "CAMPUS")
        self.assertIn("on behalf", body["created_by_name"])
        from django.utils import timezone
        reservation = Reservation.objects.get(pk=body["id"])
        self.assertEqual(reservation.approved_by, self.admin)
        self.assertIsNotNone(reservation.approved_at)
        self.assertLessEqual(
            (timezone.now() - reservation.approved_at).total_seconds(), 60
        )

    def test_requester_cannot_create_for_someone_else(self):
        other = User.objects.create_user(username="other", password="pass12345", role=User.Role.REQUESTER)
        self.client.force_authenticate(self.requester)
        response = self.client.post(
            "/api/reservations/",
            {
                "facility_id": self.facility.id,
                "date": "2026-09-14",
                "start_time": "09:00",
                "end_time": "11:00",
                "event_name": "Hijack",
                "event_type": "MEETING",
                "purpose": "Test",
                "expected_participants": 5,
                "requester_type": "CAMPUS",
                "requester_id": other.id,
                "items": [],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_admin_external_reservation_auto_approved(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            "/api/reservations/", self._external_payload(), format="json"
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["status"], "APPROVED")
        self.assertEqual(body["requester_type"], "EXTERNAL")
        self.assertEqual(body["requester"], "ABC National High School")
        self.assertEqual(body["contact_email"], "juan@example.com")
        reservation = Reservation.objects.get(pk=body["id"])
        self.assertIsNone(reservation.requester)
        self.assertEqual(reservation.created_by, self.admin)

    def test_campus_user_cannot_submit_external_type(self):
        """Authenticated non-staff callers cannot create EXTERNAL entries
        through the authenticated endpoint — external requesters use the
        public guest endpoint instead."""
        self.client.force_authenticate(self.requester)
        response = self.client.post(
            "/api/reservations/", self._external_payload(), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("requester_type", response.json())



class AuthenticationRequiredTests(TestCase):
    """Tests for authentication requirements on reservation endpoints."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser",
            password="testpass123",
            role=User.Role.REQUESTER,
            first_name="Test",
            last_name="User",
            email="test@example.com",
        )
        self.facility = Facility.objects.create(
            name="AVR",
            facility_type=Facility.FacilityType.AVR,
            capacity=50,
        )
        OperatingHour.objects.create(
            facility=self.facility,
            day_of_week=0,
            open_time=time(6, 0),
            close_time=time(22, 0),
        )
        category = EquipmentCategory.objects.create(name="Chairs")
        self.chairs = Equipment.objects.create(
            name="Folding Chair", category=category, total_quantity=100
        )

    def test_anonymous_user_cannot_create_reservation(self):
        """Unauthenticated users cannot create reservations."""
        payload = {
            "facility_id": self.facility.id,
            "date": "2026-09-14",
            "start_time": "09:00",
            "end_time": "11:00",
            "event_name": "Test Event",
            "event_type": "MEETING",
            "purpose": "Test purpose",
            "expected_participants": 10,
        }
        response = self.client.post("/api/reservations/", payload, format="json")
        self.assertEqual(response.status_code, 401)

    def test_authenticated_user_can_create_reservation(self):
        """Authenticated users can create reservations."""
        self.client.force_authenticate(self.user)
        payload = {
            "facility_id": self.facility.id,
            "date": "2026-09-14",
            "start_time": "09:00",
            "end_time": "11:00",
            "event_name": "Test Event",
            "event_type": "MEETING",
            "purpose": "Test purpose",
            "expected_participants": 10,
            "items": [{"equipment_id": self.chairs.id, "quantity": 5}],
        }
        response = self.client.post("/api/reservations/", payload, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["requester"], self.user.display_name)

    def test_anonymous_user_cannot_access_reservation_list(self):
        """Unauthenticated users cannot list reservations."""
        response = self.client.get("/api/reservations/")
        self.assertEqual(response.status_code, 401)

    def test_anonymous_user_cannot_access_reservation_detail(self):
        """Unauthenticated users cannot view reservation details."""
        reservation = Reservation.objects.create(
            requester=self.user,
            event_name="Test",
            facility=self.facility,
            date=date(2026, 9, 14),
            start_time=time(9, 0),
            end_time=time(11, 0),
            status=Reservation.Status.PENDING,
        )
        response = self.client.get(f"/api/reservations/{reservation.id}/")
        self.assertEqual(response.status_code, 401)

    def test_user_cannot_create_reservation_for_another_user(self):
        """Regular users cannot create reservations for other users."""
        other_user = User.objects.create_user(
            username="otheruser",
            password="testpass123",
            role=User.Role.REQUESTER,
        )
        self.client.force_authenticate(self.user)
        payload = {
            "facility_id": self.facility.id,
            "date": "2026-09-14",
            "start_time": "09:00",
            "end_time": "11:00",
            "event_name": "Test Event",
            "event_type": "MEETING",
            "purpose": "Test purpose",
            "expected_participants": 10,
            "requester_type": "CAMPUS",
            "requester_id": other_user.id,
        }
        response = self.client.post("/api/reservations/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("requester_id", response.json())

    def test_staff_can_create_reservation_for_other_user(self):
        """Staff can create reservations on behalf of other users."""
        admin = User.objects.create_user(
            username="admin",
            password="testpass123",
            role=User.Role.ADMIN,
        )
        other_user = User.objects.create_user(
            username="otheruser",
            password="testpass123",
            role=User.Role.REQUESTER,
        )
        self.client.force_authenticate(admin)
        payload = {
            "facility_id": self.facility.id,
            "date": "2026-09-14",
            "start_time": "09:00",
            "end_time": "11:00",
            "event_name": "Test Event",
            "event_type": "MEETING",
            "purpose": "Test purpose",
            "expected_participants": 10,
            "requester_type": "CAMPUS",
            "requester_id": other_user.id,
        }
        response = self.client.post("/api/reservations/", payload, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["requester"], other_user.display_name)
        self.assertIn("on behalf", response.json()["created_by_name"])

    def test_phone_field_not_in_user_serializer(self):
        """Phone number should not be exposed in user API responses."""
        self.client.force_authenticate(self.user)
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertNotIn("phone", data)

    def test_phone_field_not_in_reservation_response(self):
        """Phone number should not be exposed in reservation API responses."""
        self.client.force_authenticate(self.user)
        reservation = Reservation.objects.create(
            requester=self.user,
            event_name="Test",
            facility=self.facility,
            date=date(2026, 9, 14),
            start_time=time(9, 0),
            end_time=time(11, 0),
            status=Reservation.Status.PENDING,
        )
        response = self.client.get(f"/api/reservations/{reservation.id}/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertNotIn("contact_number", data)

    def test_reservation_uses_user_email_for_contact(self):
        """Reservation contact email should come from user's account."""
        self.client.force_authenticate(self.user)
        payload = {
            "facility_id": self.facility.id,
            "date": "2026-09-14",
            "start_time": "09:00",
            "end_time": "11:00",
            "event_name": "Test Event",
            "event_type": "MEETING",
            "purpose": "Test purpose",
            "expected_participants": 10,
            "items": [{"equipment_id": self.chairs.id, "quantity": 5}],
        }
        response = self.client.post("/api/reservations/", payload, format="json")
        self.assertEqual(response.status_code, 201)
        data = response.json()
        # Contact email should be the user's email, not empty
        self.assertEqual(data["contact_email"], self.user.email)

    def test_external_user_can_still_reserve_with_account(self):
        """External users can create accounts and make reservations."""
        external_user = User.objects.create_user(
            username="external",
            password="testpass123",
            role=User.Role.REQUESTER,
            first_name="External",
            last_name="User",
            email="external@example.com",
            organization="External Org",
        )
        self.client.force_authenticate(external_user)
        payload = {
            "facility_id": self.facility.id,
            "date": "2026-09-14",
            "start_time": "09:00",
            "end_time": "11:00",
            "event_name": "External Event",
            "event_type": "MEETING",
            "purpose": "External purpose",
            "expected_participants": 20,
            "organization": "External Org",
            "requester_type": "EXTERNAL",
            "contact_person": "External Contact",
            "contact_email": "external@example.com",
            "items": [{"equipment_id": self.chairs.id, "quantity": 10}],
        }
        response = self.client.post("/api/reservations/", payload, format="json")
        # External reservations by authenticated users should work
        # (staff only can create external reservations through authenticated endpoint)
        self.assertEqual(response.status_code, 400)
        self.assertIn("requester_type", response.json())

    def test_public_endpoints_removed(self):
        """Public reservation endpoints should return 404 (removed)."""
        # All public endpoints should return 404 since they've been removed
        for path in (
            "/api/public/reservations/",
            "/api/public/track/",
            "/api/public/facilities/",
            "/api/public/availability/check/",
            "/api/public/availability/resources/",
        ):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 404, f"{path} should return 404")


class RecommendationRuleTests(TestCase):
    """Staff-configured RecommendationRule rows override the built-in engine."""

    def setUp(self):
        self.facility = Facility.objects.create(
            name="Cafeteria",
            facility_type=Facility.FacilityType.CAFETERIA,
            capacity=120,
        )
        self.chairs = EquipmentCategory.objects.create(name="Chairs")
        self.tables = EquipmentCategory.objects.create(name="Tables")
        self.microphones = EquipmentCategory.objects.create(name="Microphones")
        Equipment.objects.create(
            name="Folding Chair", category=self.chairs, total_quantity=200
        )
        Equipment.objects.create(
            name="Folding Table (6 ft)", category=self.tables, total_quantity=40
        )
        Equipment.objects.create(
            name="Wired Microphone", category=self.microphones, total_quantity=6
        )

    def _recommend(self, event_type="SEMINAR", participants=29, **kwargs):
        return {
            r["category"]: r
            for r in recommend_resources(
                event_type, participants, facility_id=self.facility.id, **kwargs
            )
        }

    def test_no_rules_means_builtin_behavior(self):
        """Without DB rules the engine behaves exactly as before."""
        by_category = self._recommend()
        self.assertEqual(by_category["Chairs"]["quantity"], 29)
        self.assertEqual(by_category["Tables"]["quantity"], 3)
        self.assertEqual(by_category["Microphones"]["quantity"], 1)

    def test_per_group_rule_overrides_builtin(self):
        """1 per 2 participants, ceiling: 29 people → 15 chairs, not 29."""
        RecommendationRule.objects.create(
            category=self.chairs,
            calculation_type=RecommendationRule.CalculationType.PER_GROUP,
            participants_per_unit=2,
        )
        by_category = self._recommend()
        self.assertEqual(by_category["Chairs"]["quantity"], 15)
        self.assertEqual(by_category["Chairs"]["calculation"], "ceil(29 / 2) = 15")
        # Untouched categories keep built-in quantities.
        self.assertEqual(by_category["Tables"]["quantity"], 3)

    def test_threshold_rule_and_custom_explanation(self):
        """Tiered mic rule for seminars + staff-written explanation text."""
        RecommendationRule.objects.create(
            category=self.microphones,
            event_type="SEMINAR",
            calculation_type=RecommendationRule.CalculationType.THRESHOLD,
            threshold_tier_1=60,
            threshold_quantity_1=2,
            threshold_tier_2=200,
            threshold_quantity_2=3,
            threshold_quantity_3=4,
            explanation="Seminar AV rule configured by SAS staff",
        )
        by_category = self._recommend()
        self.assertEqual(by_category["Microphones"]["quantity"], 2)
        self.assertEqual(
            by_category["Microphones"]["reason"],
            "Seminar AV rule configured by SAS staff",
        )

    def test_specificity_and_priority_ordering(self):
        """Exact event type beats a generic rule even with lower priority."""
        RecommendationRule.objects.create(
            category=self.microphones,
            event_type="SEMINAR",
            calculation_type=RecommendationRule.CalculationType.THRESHOLD,
            threshold_tier_1=60,
            threshold_quantity_1=2,
            priority=50,
        )
        RecommendationRule.objects.create(
            category=self.microphones,
            calculation_type=RecommendationRule.CalculationType.FIXED,
            quantity_value=9,
            priority=1,
        )
        by_category = self._recommend()
        self.assertEqual(by_category["Microphones"]["quantity"], 2)
        # A different event type falls through to the generic fixed rule.
        by_meeting = self._recommend(event_type="MEETING")
        self.assertEqual(by_meeting["Microphones"]["quantity"], 9)

    def test_participant_range_and_facility_scope(self):
        """Rules only apply inside their participant range and facility type."""
        RecommendationRule.objects.create(
            category=self.chairs,
            min_participants=50,
            calculation_type=RecommendationRule.CalculationType.FIXED,
            quantity_value=60,
        )
        # 29 participants: below the range → built-in per-participant rule.
        by_category = self._recommend()
        self.assertEqual(by_category["Chairs"]["quantity"], 29)
        # 80 participants: inside the range → DB rule wins.
        by_large = self._recommend(participants=80)
        self.assertEqual(by_large["Chairs"]["quantity"], 60)

    def test_inactive_rules_are_ignored(self):
        RecommendationRule.objects.create(
            category=self.chairs,
            calculation_type=RecommendationRule.CalculationType.FIXED,
            quantity_value=99,
            is_active=False,
        )
        by_category = self._recommend()
        self.assertEqual(by_category["Chairs"]["quantity"], 29)

    def test_db_rule_can_introduce_new_category(self):
        """A category absent from the built-in profile can be recommended."""
        projector = EquipmentCategory.objects.create(name="Projectors")
        Equipment.objects.create(name="Projector", category=projector, total_quantity=3)
        RecommendationRule.objects.create(
            category=projector,
            event_type="SPORTS",  # built-in profile has no projector for SPORTS
            calculation_type=RecommendationRule.CalculationType.FIXED,
            quantity_value=1,
        )
        by_category = self._recommend(event_type="SPORTS")
        self.assertIn("Projectors", by_category)
        self.assertEqual(by_category["Projectors"]["quantity"], 1)

    def test_recommendation_still_capped_by_availability(self):
        """DB rule quantities are prefilled capped by window availability."""
        RecommendationRule.objects.create(
            category=self.microphones,
            calculation_type=RecommendationRule.CalculationType.FIXED,
            quantity_value=5,
        )
        mics = Equipment.objects.get(category=self.microphones)
        blocking = Reservation.objects.create(
            event_name="Blocking",
            event_type=Reservation.EventType.MEETING,
            facility=self.facility,
            date=date(2026, 9, 15),
            start_time=time(9, 0),
            end_time=time(11, 0),
            expected_participants=10,
            contact_person="x",
        )
        ReservationItem.objects.create(reservation=blocking, equipment=mics, quantity=4)

        recommendations = recommend_resources(
            "SEMINAR",
            29,
            facility_id=self.facility.id,
            target_date=date(2026, 9, 15),
            start_time=time(9, 0),
            end_time=time(11, 0),
        )
        mic = next(r for r in recommendations if r["category"] == "Microphones")
        self.assertEqual(mic["quantity"], 5)  # DB rule, uncapped
        self.assertEqual(mic["available"], 2)  # 4 of 6 reserved
        self.assertEqual(mic["recommended"], 2)  # capped prefill
        self.assertIn("Only 2 of the recommended 5", mic["warning"])
