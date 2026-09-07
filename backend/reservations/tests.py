from datetime import date, datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from equipment.models import Equipment, EquipmentCategory, MaintenanceRecord
from facilities.models import Facility, OperatingHour
from .models import Reservation, ReservationItem
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
            contact_number="0917 123 4567",
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

    # ------------------------------------------------------------------
    # Public guest flow
    # ------------------------------------------------------------------

    def test_guest_reservation_requires_no_account_and_stays_pending(self):
        before = Reservation.objects.count()
        response = self.client.post(
            "/api/public/reservations/", self._external_payload(), format="json"
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertTrue(body["reservation_id"].startswith("SAS-"))
        self.assertEqual(body["status"], "PENDING")
        self.assertEqual(Reservation.objects.count(), before + 1)
        reservation = Reservation.objects.get(reservation_id=body["reservation_id"])
        self.assertIsNone(reservation.requester)
        self.assertEqual(reservation.requester_type, Reservation.RequesterType.EXTERNAL)
        self.assertIsNone(reservation.created_by)

    def test_guest_reservation_requires_contact_fields(self):
        for field in ("organization", "contact_person", "contact_number", "contact_email"):
            payload = self._external_payload()
            payload[field] = ""
            response = self.client.post("/api/public/reservations/", payload, format="json")
            self.assertEqual(response.status_code, 400, field)

    def test_guest_reservation_conflict_returns_409(self):
        # Block the slot first via an authenticated campus reservation.
        self.client.force_authenticate(self.requester)
        self.client.post(
            "/api/reservations/",
            {
                "facility_id": self.facility.id,
                "date": "2026-09-14",
                "start_time": "13:00",
                "end_time": "15:00",
                "event_name": "Campus event",
                "event_type": "SPORTS",
                "purpose": "Practice",
                "expected_participants": 30,
                "items": [],
            },
            format="json",
        )
        self.client.force_authenticate(None)
        response = self.client.post(
            "/api/public/reservations/",
            self._external_payload(start_time="14:00", end_time="16:00"),
            format="json",
        )
        self.assertEqual(response.status_code, 409)

    def test_track_reservation_with_code_and_email(self):
        created = self.client.post(
            "/api/public/reservations/", self._external_payload(), format="json"
        ).json()
        code = created["reservation_id"]

        # Correct code + email -> full tracking payload.
        response = self.client.post(
            "/api/public/track/",
            {"reservation_code": code, "email": "juan@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["reservation_id"], code)
        self.assertEqual(body["status"], "PENDING")
        self.assertEqual(body["organization"], "ABC National High School")
        self.assertEqual(body["facility"], "Gymnasium")
        # Restricted payload: no internal/approval data.
        self.assertNotIn("checkin_code", body)
        self.assertNotIn("events", body)
        self.assertNotIn("notes", body)

    def test_track_reservation_requires_matching_email(self):
        created = self.client.post(
            "/api/public/reservations/", self._external_payload(), format="json"
        ).json()
        wrong = self.client.post(
            "/api/public/track/",
            {"reservation_code": created["reservation_id"], "email": "wrong@example.com"},
            format="json",
        )
        self.assertEqual(wrong.status_code, 404)
        wrong_code = self.client.post(
            "/api/public/track/",
            {"reservation_code": "SAS-2026-99999", "email": "juan@example.com"},
            format="json",
        )
        self.assertEqual(wrong_code.status_code, 404)

    def test_track_shows_checked_in_status(self):
        created = self.client.post(
            "/api/public/reservations/", self._external_payload(), format="json"
        ).json()
        reservation = Reservation.objects.get(reservation_id=created["reservation_id"])
        reservation.status = Reservation.Status.ACTIVE
        reservation.save(update_fields=["status"])

        response = self.client.post(
            "/api/public/track/",
            {"reservation_code": reservation.reservation_id, "email": "juan@example.com"},
            format="json",
        )
        self.assertEqual(response.json()["status"], "CHECKED_IN")

    def test_public_endpoints_cannot_list_or_modify_reservations(self):
        """Guests must never reach the authenticated reservation API."""
        self.client.post("/api/public/reservations/", self._external_payload(), format="json")
        # Unauthenticated access to the authenticated endpoints is rejected.
        for method, path in (
            ("get", "/api/reservations/"),
            ("post", "/api/reservations/"),
            ("get", "/api/reservations/users/"),
        ):
            response = getattr(self.client, method)(path, format="json")
            self.assertEqual(response.status_code, 401, path)

    def test_user_search_is_staff_only(self):
        self.client.force_authenticate(self.requester)
        response = self.client.get("/api/reservations/users/?search=juan")
        self.assertEqual(response.status_code, 403)

        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/reservations/users/?search=juan")
        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertTrue(any(r["id"] == self.requester.id for r in results))

    def test_requester_type_filter(self):
        self.client.force_authenticate(self.admin)
        # One external + one campus.
        self.client.post("/api/reservations/", self._external_payload(), format="json")
        self.client.post(
            "/api/reservations/",
            {
                "facility_id": self.facility.id,
                "date": "2026-09-21",
                "start_time": "09:00",
                "end_time": "11:00",
                "event_name": "Campus meeting",
                "event_type": "MEETING",
                "purpose": "Planning",
                "expected_participants": 10,
                "items": [],
            },
            format="json",
        )
        external = self.client.get("/api/reservations/?requester_type=EXTERNAL")
        self.assertEqual(external.json()["count"], 1)
        self.assertEqual(
            external.json()["results"][0]["requester_type"], "EXTERNAL"
        )
        campus = self.client.get("/api/reservations/?requester_type=CAMPUS")
        self.assertEqual(campus.json()["count"], 1)

    def test_public_facilities_and_availability(self):
        response = self.client.get("/api/public/facilities/")
        self.assertEqual(response.status_code, 200)
        names = [f["name"] for f in response.json()["results"]]
        self.assertIn("Gymnasium", names)

        response = self.client.post(
            "/api/public/availability/check/",
            {
                "facility_id": self.facility.id,
                "date": "2026-09-14",
                "start_time": "09:00",
                "end_time": "11:00",
                "items": [],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["overall"]["ok"])

    def test_public_recommendations(self):
        category = EquipmentCategory.objects.create(name="Chairs")
        Equipment.objects.create(name="Folding Chair", category=category, total_quantity=200)
        response = self.client.post(
            "/api/public/availability/resources/",
            {"event_type": "SPORTS", "expected_participants": 100},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["recommendations"])