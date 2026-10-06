"""Tests for automatic reservation expiration and the rebook flow.

Covers the full lifecycle: a PENDING reservation whose scheduled *event start
time* is reached becomes EXPIRED (server-side, time-zone aware); only PENDING
ever expires; an expired reservation can no longer be approved, checked in,
rejected, reopened, edited, or delete; it stops blocking availability; and a
new reservation can be created from it (by staff as a "rebook", by the
requester as a "request new schedule") while the original stays untouched.
"""

from datetime import date, datetime, time, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from analytics.services import summary
from facilities.models import Facility, OperatingHour
from reservations.models import Reservation
from reservations.services import expiration, workflow
from reservations.services.availability import check_availability

User = get_user_model()


class ExpirationTestCase(TestCase):
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
        # Open every day so tests never depend on the weekday.
        for weekday in range(7):
            OperatingHour.objects.create(
                facility=self.facility,
                day_of_week=weekday,
                open_time=time(0, 0),
                close_time=time(23, 59),
            )

    # -- factories ---------------------------------------------------------

    def overdue_pending(self, **overrides):
        """A PENDING reservation whose event started yesterday (always past)."""
        defaults = dict(
            requester=self.requester,
            event_name="Students Seminar",
            facility=self.facility,
            date=timezone.localdate() - timedelta(days=1),
            start_time=time(8, 0),
            end_time=time(12, 0),
            status=Reservation.Status.PENDING,
        )
        defaults.update(overrides)
        return Reservation.objects.create(**defaults)

    def future_pending(self, **overrides):
        defaults = dict(
            requester=self.requester,
            event_name="Future Event",
            facility=self.facility,
            date=timezone.localdate() + timedelta(days=5),
            start_time=time(9, 0),
            end_time=time(11, 0),
            status=Reservation.Status.PENDING,
        )
        defaults.update(overrides)
        return Reservation.objects.create(**defaults)

    def future_payload(self, **overrides):
        payload = dict(
            facility_id=self.facility.id,
            date=(timezone.localdate() + timedelta(days=3)).isoformat(),
            start_time="09:00",
            end_time="11:00",
            event_name="Rebooked Event",
            event_type="SEMINAR",
            organization="SAS",
            purpose="Replacement schedule",
            expected_participants=20,
            items=[],
        )
        payload.update(overrides)
        return payload

    def expired(self):
        reservation = self.overdue_pending()
        expiration.expire_overdue_reservations()
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.EXPIRED)
        return reservation

    # -- 1. pending becomes expired at the event start ---------------------

    def test_overdue_pending_becomes_expired(self):
        reservation = self.overdue_pending()
        count = expiration.expire_overdue_reservations()
        self.assertEqual(count, 1)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.EXPIRED)

    def test_pending_in_the_future_stays_pending(self):
        reservation = self.future_pending()
        self.assertEqual(expiration.expire_overdue_reservations(), 0)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.PENDING)

    def test_expiration_is_time_zone_aware_of_event_start(self):
        manila = timezone.get_current_timezone()
        reservation = Reservation.objects.create(
            requester=self.requester,
            event_name="Boundary",
            facility=self.facility,
            date=date(2026, 10, 3),
            start_time=time(8, 0),
            end_time=time(12, 0),
            status=Reservation.Status.PENDING,
        )
        # 7:59 AM Asia/Manila — one minute before the event: still pending.
        one_minute_before = timezone.make_aware(
            datetime(2026, 10, 3, 7, 59), manila
        )
        with mock.patch(
            "django.utils.timezone.now", return_value=one_minute_before
        ):
            self.assertFalse(expiration.expire_reservation(reservation))
        self.assertEqual(reservation.status, Reservation.Status.PENDING)

        # Exactly 8:00 AM Asia/Manila — the event has started: expired.
        at_start = timezone.make_aware(datetime(2026, 10, 3, 8, 0), manila)
        with mock.patch("django.utils.timezone.now", return_value=at_start):
            self.assertTrue(expiration.expire_reservation(reservation))
        self.assertEqual(reservation.status, Reservation.Status.EXPIRED)

    def test_expiration_records_a_system_timeline_event(self):
        reservation = self.expired()
        event = reservation.events.get(event_type="EXPIRED")
        self.assertIsNone(event.actor)
        self.assertEqual(event.from_status, Reservation.Status.PENDING)
        self.assertEqual(event.to_status, Reservation.Status.EXPIRED)
        self.assertIn("not approved before the scheduled event time", event.message)

    def test_expiration_is_idempotent(self):
        reservation = self.expired()
        self.assertFalse(expiration.expire_reservation(reservation))
        self.assertEqual(reservation.events.filter(event_type="EXPIRED").count(), 1)

    # -- 2. only PENDING ever expires --------------------------------------

    def test_only_pending_statuses_expire(self):
        for status_value in (
            Reservation.Status.APPROVED,
            Reservation.Status.ACTIVE,
            Reservation.Status.REJECTED,
            Reservation.Status.CANCELLED,
            Reservation.Status.COMPLETED,
        ):
            with self.subTest(status=status_value):
                reservation = self.overdue_pending(status=status_value)
                self.assertFalse(expiration.expire_reservation(reservation))
                reservation.refresh_from_db()
                self.assertEqual(reservation.status, status_value)

    # -- 3. approve protection ---------------------------------------------

    def test_workflow_refuses_to_approve_expired(self):
        reservation = self.expired()
        with self.assertRaisesMessage(
            ValueError, "This reservation has expired and can no longer be approved."
        ):
            workflow.approve_reservation(reservation, self.admin)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.EXPIRED)

    def test_approve_endpoint_expires_stale_pending_and_refuses(self):
        reservation = self.overdue_pending()
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            f"/api/reservations/{reservation.id}/approve/", {}, format="json"
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(
            response.json()["detail"],
            "This reservation has expired and can no longer be approved.",
        )
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.EXPIRED)
        self.assertIsNone(reservation.approved_by)

    def test_requester_cannot_approve(self):
        reservation = self.future_pending()
        self.client.force_authenticate(self.requester)
        response = self.client.post(
            f"/api/reservations/{reservation.id}/approve/", {}, format="json"
        )
        self.assertEqual(response.status_code, 403)

    def test_expired_cannot_be_rejected_or_reopened(self):
        reservation = self.expired()
        self.client.force_authenticate(self.admin)
        rejected = self.client.post(
            f"/api/reservations/{reservation.id}/reject/",
            {"reason": "too late"},
            format="json",
        )
        self.assertEqual(rejected.status_code, 400, rejected.content)
        reopened = self.client.post(
            f"/api/reservations/{reservation.id}/request_changes/",
            {"message": "please fix"},
            format="json",
        )
        self.assertEqual(reopened.status_code, 400, reopened.content)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.EXPIRED)

    # -- 4. check-in protection --------------------------------------------

    def test_expired_cannot_be_checked_in(self):
        reservation = self.expired()
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            f"/api/reservations/{reservation.id}/check_in/", {}, format="json"
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(
            response.json()["detail"],
            "This reservation has expired and can no longer be checked in.",
        )
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.EXPIRED)
        self.assertIsNone(reservation.checked_in_at)

    # -- 5. expired never blocks availability ------------------------------

    def test_expired_reservation_does_not_block_availability(self):
        target = timezone.localdate() + timedelta(days=2)
        Reservation.objects.create(
            requester=self.requester,
            event_name="Old expired",
            facility=self.facility,
            date=target,
            start_time=time(9, 0),
            end_time=time(11, 0),
            status=Reservation.Status.EXPIRED,
        )
        report = check_availability(
            self.facility.id, target, time(9, 0), time(11, 0)
        )
        self.assertTrue(report["overall"]["ok"])
        self.assertEqual(report["facility"]["conflicts"], [])

    def test_pending_reservation_still_blocks_availability(self):
        target = timezone.localdate() + timedelta(days=2)
        Reservation.objects.create(
            requester=self.requester,
            event_name="Live pending",
            facility=self.facility,
            date=target,
            start_time=time(9, 0),
            end_time=time(11, 0),
            status=Reservation.Status.PENDING,
        )
        report = check_availability(
            self.facility.id, target, time(9, 0), time(11, 0)
        )
        self.assertFalse(report["overall"]["ok"])

    # -- 6. admin rebook ----------------------------------------------------

    def test_admin_can_rebook_expired_reservation(self):
        original = self.expired()
        original_date = original.date
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            "/api/reservations/",
            self.future_payload(
                rebooked_from_id=original.id, requester_id=self.requester.id
            ),
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertNotEqual(body["reservation_id"], original.reservation_id)
        self.assertTrue(body["reservation_id"].startswith("SAS-"))
        # The new reservation still needs normal approval — never auto-approved
        # just because an administrator created it from an expired one.
        self.assertEqual(body["status"], "PENDING")
        self.assertEqual(body["rebooked_from"], original.id)
        self.assertEqual(body["rebooked_from_reference"], original.reservation_id)

        original.refresh_from_db()
        self.assertEqual(original.status, Reservation.Status.EXPIRED)
        self.assertEqual(original.date, original_date)
        self.assertIsNone(original.approved_by)
        self.assertTrue(
            original.events.filter(event_type="REBOOKED").exists()
        )
        event = original.events.get(event_type="REBOOKED")
        self.assertIn(body["reservation_id"], event.message)

        # The original links forward to the new reservation.
        detail = self.client.get(f"/api/reservations/{original.id}/")
        self.assertEqual(
            detail.json()["rescheduled_to"]["reservation_id"],
            body["reservation_id"],
        )

    def test_requester_can_request_a_new_schedule(self):
        original = self.expired()
        self.client.force_authenticate(self.requester)
        response = self.client.post(
            "/api/reservations/",
            self.future_payload(rebooked_from_id=original.id),
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["status"], "PENDING")
        self.assertEqual(body["rebooked_from"], original.id)
        original.refresh_from_db()
        self.assertTrue(
            original.events.filter(event_type="NEW_SCHEDULE_REQUESTED").exists()
        )
        self.assertEqual(original.status, Reservation.Status.EXPIRED)

    def test_requester_cannot_rebook_someone_elses_reservation(self):
        original = self.expired()
        self.client.force_authenticate(self.other)
        response = self.client.post(
            "/api/reservations/",
            self.future_payload(rebooked_from_id=original.id),
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("rebooked_from_id", response.json())

    def test_cannot_rebook_a_non_expired_reservation(self):
        original = self.future_pending()
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            "/api/reservations/",
            self.future_payload(rebooked_from_id=original.id),
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("rebooked_from_id", response.json())

    def test_rebook_conflict_is_rejected(self):
        target = timezone.localdate() + timedelta(days=3)
        Reservation.objects.create(
            requester=self.other,
            event_name="Existing approved",
            facility=self.facility,
            date=target,
            start_time=time(9, 0),
            end_time=time(11, 0),
            status=Reservation.Status.APPROVED,
        )
        original = self.expired()
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            "/api/reservations/",
            self.future_payload(
                rebooked_from_id=original.id, date=target.isoformat()
            ),
            format="json",
        )
        self.assertEqual(response.status_code, 409, response.content)

    # -- 7. expired reservations are read-only -----------------------------

    def test_requester_cannot_edit_expired_reservation(self):
        reservation = self.expired()
        self.client.force_authenticate(self.requester)
        response = self.client.patch(
            f"/api/reservations/{reservation.id}/",
            {"status": "PENDING", "event_name": "Hijacked"},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.EXPIRED)
        self.assertEqual(reservation.event_name, "Students Seminar")

    # -- 8. history / filters ----------------------------------------------

    def test_expired_stays_visible_in_history_and_counts(self):
        reservation = self.expired()
        self.client.force_authenticate(self.requester)
        listing = self.client.get("/api/reservations/?status=EXPIRED")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["count"], 1)
        self.assertEqual(
            listing.json()["results"][0]["reservation_id"],
            reservation.reservation_id,
        )
        self.assertIn(
            "not approved before the scheduled event time",
            listing.json()["results"][0]["status_reason"],
        )

        counts = self.client.get("/api/reservations/counts/")
        self.assertEqual(counts.status_code, 200)
        self.assertEqual(counts.json()["EXPIRED"], 1)
        self.assertEqual(counts.json()["ALL"], 1)

    def test_admin_sees_expired_reservations(self):
        reservation = self.expired()
        self.client.force_authenticate(self.admin)
        listing = self.client.get("/api/reservations/?status=EXPIRED")
        self.assertEqual(listing.json()["count"], 1)
        self.assertEqual(
            listing.json()["results"][0]["reservation_id"],
            reservation.reservation_id,
        )

    # -- 9. dashboard + management command ---------------------------------

    def test_dashboard_summary_expires_stale_pending(self):
        reservation = self.overdue_pending()
        payload = summary(user=self.admin)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.EXPIRED)
        self.assertEqual(payload["pending_requests"], 0)

    def test_management_command_expires_overdue(self):
        reservation = self.overdue_pending()
        call_command("expire_reservations")
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.EXPIRED)
