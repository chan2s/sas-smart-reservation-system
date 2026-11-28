"""Tests for the public booked-dates calendar endpoint.

The reservation date picker and its Booked Dates view show pending requests
alongside approved reservations so other requesters can see a facility or
resource has already been requested — while availability keeps treating only
approved reservations as confirmed bookings (``AVAILABILITY_BLOCKING_STATUSES``).
Rejected, cancelled, expired, and no-show reservations never appear, and the
payload stays free of requester identity and contact details.
"""

from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from equipment.models import Equipment, EquipmentCategory
from facilities.models import Facility, OperatingHour
from reservations.models import Reservation, ReservationItem

User = get_user_model()

# The complete public payload: schedule, workflow status, and resource names.
PUBLIC_EVENT_KEYS = {
    "event_name",
    "facility_name",
    "date",
    "start_time",
    "end_time",
    "status",
    "status_label",
    "resources",
}


class PublicBookedDatesTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="requester",
            password="pass12345",
            role=User.Role.REQUESTER,
            first_name="Juan",
            last_name="Dela Cruz",
            email="requester@example.com",
        )
        self.facility = Facility.objects.create(
            name="Gymnasium",
            facility_type=Facility.FacilityType.GYMNASIUM,
            capacity=200,
        )
        OperatingHour.objects.create(
            facility=self.facility,
            day_of_week=0,
            open_time=time(8, 0),
            close_time=time(17, 0),
        )
        self.sound_system = Equipment.objects.create(
            name="Sound System",
            category=EquipmentCategory.objects.create(name="Audio"),
            total_quantity=1,
        )
        self.led_wall = Equipment.objects.create(
            name="LED Wall",
            category=EquipmentCategory.objects.create(name="Visuals"),
            total_quantity=1,
        )
        # A near-future Monday matching the operating hours above.
        self.day = timezone.localdate() + timedelta(days=1)
        while self.day.weekday() != 0:
            self.day += timedelta(days=1)

    def _reservation(self, status=Reservation.Status.PENDING, event_name="Culmination Program", **overrides):
        """A reservation carrying the private fields that must never leak."""
        reservation = Reservation.objects.create(
            requester=self.user,
            event_name=event_name,
            facility=self.facility,
            date=self.day,
            start_time=time(9, 0),
            end_time=time(11, 0),
            status=status,
            contact_person="Juan Dela Cruz",
            contact_email="juan@example.com",
            contact_phone="09171234567",
            notes="Internal setup notes",
            **overrides,
        )
        return reservation

    def _get(self, **params):
        return self.client.get(
            "/api/public/reservations/booked-dates/",
            {
                "facility_id": self.facility.id,
                "start": self.day.isoformat(),
                "end": self.day.isoformat(),
                **params,
            },
        )

    def _add_item(self, reservation, equipment, quantity=1):
        ReservationItem.objects.create(reservation=reservation, equipment=equipment, quantity=quantity)

    # ------------------------------------------------------------------
    # Visibility
    # ------------------------------------------------------------------

    def test_pending_and_approved_reservations_are_listed(self):
        pending = self._reservation(event_name="Pending Request")
        approved = self._reservation(
            status=Reservation.Status.APPROVED, event_name="Approved Event"
        )
        active = self._reservation(
            status=Reservation.Status.ACTIVE, event_name="In Progress"
        )
        response = self._get()
        self.assertEqual(response.status_code, 200, response.content)
        events = response.json()
        by_name = {event["event_name"]: event for event in events}
        self.assertEqual(
            {pending.event_name, approved.event_name, active.event_name}, set(by_name)
        )
        self.assertEqual(by_name[pending.event_name]["status"], "PENDING")
        self.assertEqual(by_name[pending.event_name]["status_label"], "Pending")
        self.assertEqual(by_name[approved.event_name]["status"], "APPROVED")
        self.assertEqual(by_name[approved.event_name]["status_label"], "Approved")
        # Schedule details accompany each status so requesters see the slots.
        self.assertEqual(by_name[pending.event_name]["start_time"], "09:00:00")
        self.assertEqual(by_name[pending.event_name]["end_time"], "11:00:00")

    def test_rejected_cancelled_expired_and_no_show_are_not_listed(self):
        for status, name in (
            (Reservation.Status.REJECTED, "Rejected Event"),
            (Reservation.Status.CANCELLED, "Cancelled Event"),
            (Reservation.Status.EXPIRED, "Expired Event"),
            (Reservation.Status.NO_SHOW, "No Show Event"),
        ):
            self._reservation(status=status, event_name=name)
        response = self._get()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json(), [])

    def test_status_transition_updates_the_calendar(self):
        reservation = self._reservation()
        self.assertEqual(self._get().json()[0]["status"], "PENDING")

        # Pending → Approved: the day keeps its entry, now confirmed.
        reservation.status = Reservation.Status.APPROVED
        reservation.save(update_fields=["status"])
        self.assertEqual(self._get().json()[0]["status"], "APPROVED")

        # Approved → Rejected: the entry disappears from the calendar.
        reservation.status = Reservation.Status.REJECTED
        reservation.save(update_fields=["status"])
        self.assertEqual(self._get().json(), [])

    # ------------------------------------------------------------------
    # Privacy
    # ------------------------------------------------------------------

    def test_response_exposes_only_public_fields(self):
        self._reservation()
        response = self._get()
        events = response.json()
        self.assertEqual(len(events), 1)
        self.assertEqual(set(events[0].keys()), PUBLIC_EVENT_KEYS)
        body = response.content.decode()
        for private in (
            "juan@example.com",
            "09171234567",
            "Internal setup notes",
            "Juan Dela Cruz",
            "requester@example.com",
        ):
            self.assertNotIn(private, body)

    # ------------------------------------------------------------------
    # Resource-specific visibility
    # ------------------------------------------------------------------

    def test_requested_resources_are_listed(self):
        reservation = self._reservation()
        self._add_item(reservation, self.sound_system)
        self._add_item(reservation, self.led_wall)
        response = self._get()
        self.assertEqual(
            response.json()[0]["resources"], ["LED Wall", "Sound System"]
        )

    def test_resource_names_are_deduplicated_across_quantities(self):
        reservation = self._reservation()
        self._add_item(reservation, self.sound_system, quantity=2)
        self.assertEqual(self._get().json()[0]["resources"], ["Sound System"])

    def test_reservation_without_resources_lists_none(self):
        self._reservation()
        self.assertEqual(self._get().json()[0]["resources"], [])

    # ------------------------------------------------------------------
    # Availability rules are unchanged
    # ------------------------------------------------------------------

    def test_pending_request_does_not_block_availability_or_new_requests(self):
        self._reservation()  # PENDING, 09:00–11:00
        # The public availability check still reports the window available.
        check = self.client.post(
            "/api/public/reservations/availability/",
            {
                "facility_id": self.facility.id,
                "date": self.day.isoformat(),
                "start_time": "09:00",
                "end_time": "11:00",
                "items": [],
            },
            format="json",
        )
        self.assertEqual(check.status_code, 200, check.content)
        self.assertTrue(check.json()["overall"]["ok"])

        # A new overlapping request is accepted, not auto-rejected: pending
        # requests inform, they never confirm a booking.
        self.client.force_authenticate(self.user)
        payload = {
            "facility_id": self.facility.id,
            "date": self.day.isoformat(),
            "start_time": "09:00",
            "end_time": "11:00",
            "event_name": "Overlapping New Request",
            "event_type": "MEETING",
            "purpose": "Overlap pending request",
            "expected_participants": 10,
            "items": [],
        }
        response = self.client.post("/api/reservations/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.content)

    def test_approved_reservation_still_blocks_availability(self):
        self._reservation(status=Reservation.Status.APPROVED)
        check = self.client.post(
            "/api/public/reservations/availability/",
            {
                "facility_id": self.facility.id,
                "date": self.day.isoformat(),
                "start_time": "09:00",
                "end_time": "11:00",
                "items": [],
            },
            format="json",
        )
        self.assertEqual(check.status_code, 200, check.content)
        body = check.json()
        # The public report strips conflict rows (they carry requester identity)
        # but the blocking verdict is unchanged: an approved reservation still
        # makes the window unavailable.
        self.assertFalse(body["overall"]["ok"])
        self.assertFalse(body["facility"]["available"])

    def test_pending_request_does_not_reduce_resource_availability(self):
        reservation = self._reservation()
        self._add_item(reservation, self.sound_system, quantity=1)
        check = self.client.post(
            "/api/public/reservations/availability/",
            {
                "facility_id": self.facility.id,
                "date": self.day.isoformat(),
                "start_time": "09:00",
                "end_time": "11:00",
                "items": [{"equipment_id": self.sound_system.id, "quantity": 1}],
            },
            format="json",
        )
        self.assertEqual(check.status_code, 200, check.content)
        self.assertTrue(check.json()["overall"]["ok"], check.content)
        item = next(
            row for row in check.json()["items"] if row["equipment_id"] == self.sound_system.id
        )
        self.assertEqual(item["available"], 1)
