"""Tests for the requester edit + resubmit workflow.

Covers the "administrator requested changes" flow end to end: the owner
revises a reservation awaiting review (schedule, details, resources) through
the dedicated ``resubmit`` action, which revalidates everything a fresh
submission goes through while keeping the reservation PENDING — never
auto-approved — and leaving the administrator's change request intact in the
timeline. Also covers the ownership/status policy (another requester and
non-pending statuses are refused), the disabled generic PUT/PATCH endpoints,
and the owner-scoped ``exclude_id`` on the availability check.
"""

from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from equipment.models import Equipment, EquipmentCategory
from facilities.models import Facility, OperatingHour
from notifications.models import Notification
from reservations.models import Reservation, ReservationEvent

User = get_user_model()


class ReservationResubmitTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="admin", password="pass12345", role=User.Role.ADMIN
        )
        self.requester = User.objects.create_user(
            username="requester", password="pass12345", role=User.Role.REQUESTER
        )
        self.other = User.objects.create_user(
            username="other", password="pass12345", role=User.Role.REQUESTER
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
        self.projector = Equipment.objects.create(
            name="Projector",
            category=EquipmentCategory.objects.create(name="Projectors"),
            total_quantity=2,
        )
        # A near-future Monday so the (Monday-only) operating hours line up and
        # reservation dates never go stale as the calendar advances.
        self.day = timezone.localdate() + timedelta(days=1)
        while self.day.weekday() != 0:
            self.day += timedelta(days=1)
        self.reservation = self._create_pending()

    def _create_pending(self, **overrides):
        """A PENDING reservation owned by self.requester, as the API creates it."""
        self.client.force_authenticate(self.requester)
        payload = dict(
            facility_id=self.facility.id,
            date=self.day.isoformat(),
            start_time="09:00",
            end_time="18:00",
            event_name="Orientation",
            event_type="ACADEMIC",
            organization="Student Affairs",
            purpose="Freshmen orientation",
            expected_participants=50,
            contact_person=self.requester.display_name,
            contact_phone="09171234567",
            notes="Bring banners",
            items=[{"equipment_id": self.chairs.id, "quantity": 50}],
        )
        payload.update(overrides)
        response = self.client.post("/api/reservations/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        return Reservation.objects.get(pk=response.json()["id"])

    def _request_changes(self, message="Please adjust the end time to 5:00 PM."):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            f"/api/reservations/{self.reservation.id}/request_changes/",
            {"message": message},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)

    def _resubmit_payload(self, **overrides):
        payload = dict(
            facility_id=self.facility.id,
            date=self.day.isoformat(),
            start_time="09:00",
            end_time="17:00",
            event_name="Orientation",
            event_type="ACADEMIC",
            purpose="Freshmen orientation",
            expected_participants=50,
            contact_person=self.requester.display_name,
            contact_phone="09171234567",
            notes="Bring banners",
            items=[{"equipment_id": self.chairs.id, "quantity": 50}],
        )
        payload.update(overrides)
        return payload

    def _resubmit(self, payload=None, user=None):
        self.client.force_authenticate(user or self.requester)
        return self.client.post(
            f"/api/reservations/{self.reservation.id}/resubmit/",
            payload or self._resubmit_payload(),
            format="json",
        )

    def test_full_change_request_workflow(self):
        """Changes requested → owner edits the end time → resubmitted, still PENDING."""
        self._request_changes("Please adjust the end time to 5:00 PM.")
        # The requester was notified about the change request...
        self.assertTrue(
            Notification.objects.filter(
                user=self.requester, title="Changes requested"
            ).exists()
        )

        response = self._resubmit()
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()

        # The status NEVER changes on resubmission: the reservation is still
        # awaiting review (never auto-approved), with the requested end time.
        self.assertEqual(body["status"], "PENDING")
        self.assertEqual(body["end_time"], "17:00")
        self.assertEqual(body["start_time"], "09:00")

        events = list(Reservation.objects.get(pk=self.reservation.pk).events.all())
        types = [event.event_type for event in events]
        self.assertIn(ReservationEvent.EventType.CHANGES_REQUESTED, types)
        self.assertIn(ReservationEvent.EventType.UPDATED, types)

        # The administrator's original message is preserved verbatim...
        changes = next(
            event
            for event in events
            if event.event_type == ReservationEvent.EventType.CHANGES_REQUESTED
        )
        self.assertEqual(changes.message, "Please adjust the end time to 5:00 PM.")
        self.assertEqual(changes.actor, self.admin)
        # ...and the revision is recorded after it, with the acting user.
        updated = events[types.index(ReservationEvent.EventType.UPDATED)]
        self.assertGreater(updated.created_at, changes.created_at)
        self.assertEqual(updated.actor, self.requester)
        self.assertEqual(updated.from_status, "PENDING")
        self.assertEqual(updated.to_status, "PENDING")
        self.assertIn("requester", updated.message)

        # Administrators are notified so the reservation is picked up again.
        self.assertTrue(
            Notification.objects.filter(
                user=self.admin, title="Reservation resubmitted"
            ).exists()
        )

    def test_edit_eligibility_flags_follow_the_workflow(self):
        """can_edit/changes_requested only hold for a pending, owned reservation."""
        self.client.force_authenticate(self.requester)

        detail = self.client.get(f"/api/reservations/{self.reservation.id}/").json()
        # A plain pending reservation is revisable by its owner, but nothing
        # asks for changes yet.
        self.assertTrue(detail["can_edit"])
        self.assertFalse(detail["changes_requested"])

        self._request_changes()
        detail = self.client.get(f"/api/reservations/{self.reservation.id}/").json()
        self.assertTrue(detail["can_edit"])
        self.assertTrue(detail["changes_requested"])

        # Once a decision is made, the reservation leaves the editable state.
        self.client.force_authenticate(self.admin)
        self.client.post(f"/api/reservations/{self.reservation.id}/approve/", {})
        detail = self.client.get(f"/api/reservations/{self.reservation.id}/").json()
        self.assertFalse(detail["can_edit"])
        self.assertFalse(detail["changes_requested"])

    def test_staff_sees_edit_eligibility_for_a_requesters_reservation(self):
        detail = self.client.get(f"/api/reservations/{self.reservation.id}/").json()
        self.assertTrue(detail["can_edit"])

    def test_resubmit_updates_resources_and_preserves_untouched_values(self):
        """Quantities/resources change as requested; everything else is kept."""
        Reservation.objects.filter(pk=self.reservation.pk).update(
            special_requirements="Legacy requirements",
            description="Legacy description",
        )
        self._request_changes()
        response = self._resubmit(
            self._resubmit_payload(
                items=[
                    {"equipment_id": self.chairs.id, "quantity": 30},
                    {"equipment_id": self.projector.id, "quantity": 1},
                ],
            )
        )
        self.assertEqual(response.status_code, 200, response.content)

        reservation = Reservation.objects.get(pk=self.reservation.pk)
        self.assertEqual(
            sorted((item.equipment_id, item.quantity) for item in reservation.items.all()),
            sorted([(self.chairs.id, 30), (self.projector.id, 1)]),
        )
        # Untouched values survive the revision (identity, affiliation, and
        # legacy free-text the form no longer collects).
        self.assertEqual(reservation.requester, self.requester)
        self.assertEqual(reservation.organization, "Student Affairs")
        self.assertEqual(reservation.contact_email, self.requester.email)
        self.assertEqual(reservation.special_requirements, "Legacy requirements")
        self.assertEqual(reservation.description, "Legacy description")
        self.assertEqual(reservation.notes, "Bring banners")
        self.assertEqual(reservation.contact_phone, "09171234567")

    def test_resubmit_conflicting_schedule_returns_409(self):
        """A conflicting booking made while awaiting review blocks the new slot."""
        self._request_changes()
        # Someone else books 15:00–17:00 in the same facility meanwhile. (Built
        # via the ORM: the create API would rightly refuse the overlap with the
        # requester's own still-held 09:00–18:00 slot.)
        Reservation.objects.create(
            facility=self.facility,
            date=self.day,
            start_time=time(15, 0),
            end_time=time(17, 0),
            event_name="Other event",
            event_type=Reservation.EventType.ACADEMIC,
            requester=self.other,
            expected_participants=10,
        )

        response = self._resubmit()
        self.assertEqual(response.status_code, 409, response.content)
        self.assertIn("availability", response.json())
        # The original schedule is untouched after the refused revision.
        reservation = Reservation.objects.get(pk=self.reservation.pk)
        self.assertEqual(reservation.end_time, time(18, 0))

    def test_other_requester_cannot_resubmit(self):
        """A non-owner can neither see nor resubmit someone else's reservation."""
        self._request_changes()
        response = self._resubmit(user=self.other)
        self.assertEqual(response.status_code, 404, response.content)
        reservation = Reservation.objects.get(pk=self.reservation.pk)
        self.assertEqual(reservation.end_time, time(18, 0))
        self.assertFalse(
            reservation.events.filter(event_type=ReservationEvent.EventType.UPDATED).exists()
        )

    def test_resubmit_refused_for_non_pending_statuses(self):
        """Only a reservation awaiting review can be edited and resubmitted."""
        self._request_changes()
        for status in (
            Reservation.Status.APPROVED,
            Reservation.Status.ACTIVE,
            Reservation.Status.COMPLETED,
            Reservation.Status.REJECTED,
            Reservation.Status.CANCELLED,
            Reservation.Status.EXPIRED,
        ):
            with self.subTest(status=status):
                Reservation.objects.filter(pk=self.reservation.pk).update(status=status)
                response = self._resubmit()
                self.assertEqual(response.status_code, 400, response.content)

    def test_resubmit_after_approval_is_refused_end_to_end(self):
        """An approval that lands before the revision wins; the edit is refused."""
        self._request_changes()
        self.client.force_authenticate(self.admin)
        self.client.post(f"/api/reservations/{self.reservation.id}/approve/", {})
        response = self._resubmit()
        self.assertEqual(response.status_code, 400, response.content)
        reservation = Reservation.objects.get(pk=self.reservation.pk)
        self.assertEqual(reservation.status, Reservation.Status.APPROVED)
        self.assertEqual(reservation.end_time, time(18, 0))

    def test_resubmit_cannot_forge_status_or_requester(self):
        """Identity/status fields are ignored — only details are writable."""
        self._request_changes()
        response = self._resubmit(
            self._resubmit_payload(
                status="APPROVED",
                requester_id=self.other.id,
                requester_type="EXTERNAL",
                organization="Forged Organization",
                contact_email="forged@example.com",
            )
        )
        self.assertEqual(response.status_code, 200, response.content)
        reservation = Reservation.objects.get(pk=self.reservation.pk)
        self.assertEqual(reservation.status, Reservation.Status.PENDING)
        self.assertEqual(reservation.requester, self.requester)
        self.assertEqual(reservation.requester_type, Reservation.RequesterType.CAMPUS)
        self.assertEqual(reservation.organization, "Student Affairs")
        self.assertEqual(reservation.contact_email, self.requester.email)

    def test_resubmit_validates_like_a_fresh_submission(self):
        """Required fields, time rules, and date rules all apply on resubmit."""
        self._request_changes()
        # End time not after start time.
        response = self._resubmit(self._resubmit_payload(start_time="17:00", end_time="17:00"))
        self.assertEqual(response.status_code, 400, response.content)
        # Past date.
        response = self._resubmit(
            self._resubmit_payload(
                date=(timezone.localdate() - timedelta(days=1)).isoformat()
            )
        )
        self.assertEqual(response.status_code, 400, response.content)
        # Missing event name.
        response = self._resubmit(self._resubmit_payload(event_name="   "))
        self.assertEqual(response.status_code, 400, response.content)
        # Zero participants.
        response = self._resubmit(self._resubmit_payload(expected_participants=0))
        self.assertEqual(response.status_code, 400, response.content)
        # Nothing was persisted by the refused attempts.
        reservation = Reservation.objects.get(pk=self.reservation.pk)
        self.assertEqual(reservation.end_time, time(18, 0))
        self.assertEqual(reservation.event_name, "Orientation")

    def test_staff_can_resubmit_on_behalf(self):
        """SAS staff keep their authorized ability to revise a pending reservation."""
        self._request_changes()
        response = self._resubmit(user=self.admin)
        self.assertEqual(response.status_code, 200, response.content)
        updated = (
            Reservation.objects.get(pk=self.reservation.pk)
            .events.filter(event_type=ReservationEvent.EventType.UPDATED)
            .latest("created_at")
        )
        self.assertEqual(updated.actor, self.admin)
        self.assertEqual(updated.message, "Reservation updated and resubmitted.")

    def test_plain_pending_reservation_can_be_revised(self):
        """A business-rule superset: the owner may revise any pending reservation."""
        response = self._resubmit()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            Reservation.objects.get(pk=self.reservation.pk).end_time, time(17, 0)
        )

    def test_generic_update_endpoints_are_disabled(self):
        """PUT/PATCH can never edit a reservation — not even by its owner."""
        self._request_changes()
        self.client.force_authenticate(self.requester)
        for method in ("put", "patch"):
            with self.subTest(method=method):
                sender = getattr(self.client, method)
                response = sender(
                    f"/api/reservations/{self.reservation.id}/",
                    self._resubmit_payload(),
                    format="json",
                )
                self.assertEqual(response.status_code, 405, response.content)
        self.assertEqual(
            Reservation.objects.get(pk=self.reservation.pk).end_time, time(18, 0)
        )

    def test_availability_check_exclude_id(self):
        """Editing owners can exclude their own reservation from the check."""
        self.client.force_authenticate(self.requester)
        base = {
            "facility_id": self.facility.id,
            "date": self.day.isoformat(),
            "start_time": "09:00",
            "end_time": "17:00",
            "items": [{"equipment_id": self.chairs.id, "quantity": 10}],
        }
        # Without the exclusion the reservation's own slot is a conflict...
        response = self.client.post("/api/availability/check/", base, format="json")
        self.assertFalse(response.json()["overall"]["ok"])
        # ...with it, the moved window is judged on its own merits.
        response = self.client.post(
            "/api/availability/check/",
            {**base, "exclude_id": self.reservation.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["overall"]["ok"])

        # Another user may never exclude someone else's reservation.
        self.client.force_authenticate(self.other)
        response = self.client.post(
            "/api/availability/check/",
            {**base, "exclude_id": self.reservation.id},
            format="json",
        )
        self.assertEqual(response.status_code, 403, response.content)
