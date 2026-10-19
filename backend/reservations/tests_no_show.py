"""Tests for the administrator no-show workflow.

Covers backend authorization, calendar-day eligibility, status guarding,
audit history, repeat/concurrent requests, check-in enforcement, serializer
eligibility flags, and status counts. The endpoint is the only way a
reservation becomes NO_SHOW — nothing in the scheduled reminder sweep ever
changes a status.
"""

from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AuditLog
from facilities.models import Facility, OperatingHour
from reservations.models import Reservation, ReservationEvent
from reservations.services import workflow

User = get_user_model()


class NoShowTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="no-show-admin", password="pass12345", role=User.Role.ADMIN
        )
        self.staff = User.objects.create_user(
            username="no-show-staff", password="pass12345", role=User.Role.STAFF
        )
        self.requester = User.objects.create_user(
            username="no-show-requester",
            password="pass12345",
            role=User.Role.REQUESTER,
        )
        self.other = User.objects.create_user(
            username="no-show-other", password="pass12345", role=User.Role.REQUESTER
        )
        self.facility = Facility.objects.create(
            name="No-Show Gym", facility_type=Facility.FacilityType.GYMNASIUM, capacity=200
        )
        for weekday in range(7):
            OperatingHour.objects.create(
                facility=self.facility,
                day_of_week=weekday,
                open_time=time(0, 0),
                close_time=time(23, 59),
            )

    def make_reservation(self, **overrides):
        defaults = dict(
            requester=self.requester,
            requester_type=Reservation.RequesterType.CAMPUS,
            event_name="Basketball Finals",
            event_type=Reservation.EventType.SPORTS,
            facility=self.facility,
            date=timezone.localdate() - timedelta(days=1),
            start_time=time(8, 0),
            end_time=time(10, 0),
            status=Reservation.Status.APPROVED,
            approved_at=timezone.make_aware(
                datetime.combine(
                    timezone.localdate() - timedelta(days=3), time(9, 0)
                )
            ),
        )
        defaults.update(overrides)
        return Reservation.objects.create(**defaults)

    def mark_no_show(self, reservation, user=None):
        self.client.force_authenticate(user or self.admin)
        return self.client.post(
            f"/api/reservations/{reservation.id}/mark-no-show/", {}, format="json"
        )

    def check_in(self, reservation, user=None, override=False):
        self.client.force_authenticate(user or self.admin)
        return self.client.post(
            f"/api/reservations/{reservation.id}/check_in/",
            {"override": override},
            format="json",
        )

    # -- happy path --------------------------------------------------------

    def test_administrator_can_mark_ended_approved_reservation_no_show(self):
        reservation = self.make_reservation()
        response = self.mark_no_show(reservation)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], Reservation.Status.NO_SHOW)
        self.assertEqual(
            response.data["message"], "Reservation successfully marked as no-show."
        )
        self.assertEqual(response.data["no_show_marked_by_name"], self.admin.display_name)

        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.NO_SHOW)
        self.assertIsNotNone(reservation.no_show_marked_at)
        self.assertEqual(reservation.no_show_marked_by, self.admin)

        event = ReservationEvent.objects.get(
            reservation=reservation,
            event_type=ReservationEvent.EventType.NO_SHOW,
        )
        self.assertEqual(event.actor, self.admin)
        self.assertEqual(event.from_status, Reservation.Status.APPROVED)
        self.assertEqual(event.to_status, Reservation.Status.NO_SHOW)
        self.assertIn("Basketball Finals", event.message)
        self.assertIn("did not check in", event.message)
        self.assertIsNotNone(event.created_at)

        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.admin,
                action=AuditLog.Action.RESERVATION_NO_SHOW,
                object_id=reservation.reservation_id,
            ).exists()
        )

    def test_sas_staff_can_mark_no_show(self):
        reservation = self.make_reservation()
        response = self.mark_no_show(reservation, user=self.staff)
        self.assertEqual(response.status_code, 200, response.data)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.NO_SHOW)

    def test_original_schedule_is_preserved_in_history(self):
        reservation = self.make_reservation()
        original_date = reservation.date
        original_start = reservation.start_time
        original_end = reservation.end_time
        self.mark_no_show(reservation)

        reservation.refresh_from_db()
        self.assertEqual(reservation.date, original_date)
        self.assertEqual(reservation.start_time, original_start)
        self.assertEqual(reservation.end_time, original_end)

    # -- eligibility / backend validation ---------------------------------

    def test_cannot_mark_future_reservation(self):
        reservation = self.make_reservation(
            date=timezone.localdate() + timedelta(days=1)
        )
        response = self.mark_no_show(reservation)

        self.assertEqual(response.status_code, 400)
        self.assertIn("day following", response.data["detail"])
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.APPROVED)
        self.assertIsNone(reservation.no_show_marked_at)

    def test_cannot_mark_on_event_day(self):
        """The reservation date itself is NOT eligible — even after its end."""
        reservation = self.make_reservation(
            date=timezone.localdate(), start_time=time(9, 0), end_time=time(10, 0)
        )
        late_on_event_day = timezone.make_aware(
            datetime.combine(reservation.date, time(23, 59))
        )
        allowed, code, _reason = workflow.no_show_eligibility(
            reservation, self.admin, now=late_on_event_day
        )
        self.assertFalse(allowed)
        self.assertEqual(code, "date_not_passed")

        response = self.mark_no_show(reservation)
        self.assertEqual(response.status_code, 400)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.APPROVED)

    def test_becomes_eligible_at_midnight_of_following_day(self):
        """Eligibility is the next CALENDAR day, not 24h after the start time."""
        reservation = self.make_reservation(
            date=timezone.localdate() - timedelta(days=1),
            start_time=time(9, 0),
            end_time=time(17, 0),
        )
        # Only minutes after the event date flipped over local midnight.
        just_after_midnight = timezone.make_aware(
            datetime.combine(timezone.localdate(), time(0, 1))
        )
        allowed, code, _reason = workflow.no_show_eligibility(
            reservation, self.admin, now=just_after_midnight
        )
        self.assertTrue(allowed, code)

    # -- check-in enforcement ---------------------------------------------

    def test_approved_reservation_today_can_still_be_checked_in(self):
        """Before the no-show window opens, the existing check-in flow works."""
        reservation = self.make_reservation(
            date=timezone.localdate(), start_time=time(0, 0), end_time=time(23, 59)
        )
        response = self.check_in(reservation, user=self.requester)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], Reservation.Status.ACTIVE)
        self.assertIsNotNone(response.data["checked_in_at"])

    def test_past_date_reservation_cannot_be_checked_in(self):
        """Direct API access cannot bypass the one-day no-show rule."""
        reservation = self.make_reservation()
        response = self.check_in(reservation, user=self.requester)
        self.assertEqual(response.status_code, 400)
        self.assertIn("date has passed", response.data["detail"])
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.APPROVED)
        self.assertIsNone(reservation.checked_in_at)

    def test_no_show_reservation_cannot_be_checked_in(self):
        reservation = self.make_reservation(
            status=Reservation.Status.NO_SHOW,
            no_show_marked_at=timezone.now(),
            no_show_marked_by=self.admin,
        )
        response = self.check_in(reservation, user=self.requester)
        self.assertEqual(response.status_code, 400)
        self.assertIn("no-show", response.data["detail"])
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.NO_SHOW)
        self.assertIsNone(reservation.checked_in_at)

    def test_cancelled_reservation_cannot_be_checked_in(self):
        reservation = self.make_reservation(status=Reservation.Status.CANCELLED)
        response = self.check_in(reservation, user=self.requester)
        self.assertEqual(response.status_code, 400)
        self.assertIn("cancelled", response.data["detail"])
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.CANCELLED)

    def test_other_requester_cannot_check_in(self):
        reservation = self.make_reservation(
            date=timezone.localdate(), start_time=time(0, 0), end_time=time(23, 59)
        )
        response = self.check_in(reservation, user=self.other)
        # A non-staff account cannot even resolve another requester's
        # reservation through the queryset, so the API answers 404 (never a
        # successful check-in); both 403 and 404 satisfy the rule.
        self.assertIn(response.status_code, (403, 404))
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.APPROVED)
        self.assertIsNone(reservation.checked_in_at)

    def test_cannot_mark_pending_reservation(self):
        # Future-dated so the existing expiration sweep does not finalize it
        # before the eligibility check runs.
        reservation = self.make_reservation(
            status=Reservation.Status.PENDING,
            date=timezone.localdate() + timedelta(days=2),
        )
        response = self.mark_no_show(reservation)
        self.assertEqual(response.status_code, 400)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.PENDING)

    def test_cannot_mark_cancelled_reservation(self):
        reservation = self.make_reservation(status=Reservation.Status.CANCELLED)
        response = self.mark_no_show(reservation)
        self.assertEqual(response.status_code, 400)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.CANCELLED)

    def test_cannot_mark_completed_reservation(self):
        reservation = self.make_reservation(status=Reservation.Status.COMPLETED)
        response = self.mark_no_show(reservation)
        self.assertEqual(response.status_code, 400)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.COMPLETED)

    def test_cannot_mark_checked_in_reservation(self):
        reservation = self.make_reservation(
            status=Reservation.Status.ACTIVE,
            checked_in_at=timezone.now() - timedelta(days=1),
        )
        response = self.mark_no_show(reservation)
        self.assertEqual(response.status_code, 400)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.ACTIVE)

    def test_cancelled_reservation_is_not_eligible_even_after_event_end(self):
        reservation = self.make_reservation(status=Reservation.Status.CANCELLED)
        allowed, code, reason = workflow.no_show_eligibility(
            reservation, self.admin
        )
        self.assertFalse(allowed)
        self.assertEqual(code, "status")
        self.assertIn("approved", reason.lower())

    def test_requester_cannot_access_admin_action(self):
        reservation = self.make_reservation()
        response = self.mark_no_show(reservation, user=self.requester)
        self.assertEqual(response.status_code, 403)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.APPROVED)

    def test_other_requester_cannot_access_admin_action(self):
        reservation = self.make_reservation()
        response = self.mark_no_show(reservation, user=self.other)
        self.assertEqual(response.status_code, 403)

    def test_invalid_reservation_id_returns_404(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            "/api/reservations/999999/mark-no-show/", {}, format="json"
        )
        self.assertEqual(response.status_code, 404)

    def test_repeated_request_is_handled_safely(self):
        reservation = self.make_reservation()
        first = self.mark_no_show(reservation)
        second = self.mark_no_show(reservation)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 400)
        self.assertIn("already been marked", second.data["detail"])
        self.assertEqual(
            ReservationEvent.objects.filter(
                reservation=reservation,
                event_type=ReservationEvent.EventType.NO_SHOW,
            ).count(),
            1,
        )
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.NO_SHOW)

    def test_stale_concurrent_requests_produce_one_transition(self):
        """Two callers holding stale instances: only the first succeeds."""
        first_copy = Reservation.objects.get(pk=self.make_reservation().pk)
        second_copy = Reservation.objects.get(pk=first_copy.pk)

        workflow.mark_no_show(first_copy, self.admin)
        with self.assertRaises(ValueError):
            workflow.mark_no_show(second_copy, self.admin)

        self.assertEqual(
            ReservationEvent.objects.filter(
                reservation_id=first_copy.pk,
                event_type=ReservationEvent.EventType.NO_SHOW,
            ).count(),
            1,
        )

    def test_check_in_wins_over_concurrent_no_show(self):
        """A check-in commit makes the stale no-show request ineligible."""
        reservation = self.make_reservation(
            date=timezone.localdate(), start_time=time(0, 0), end_time=time(23, 59)
        )
        stale = Reservation.objects.get(pk=reservation.pk)

        workflow.check_in_reservation(reservation, self.requester)
        with self.assertRaises(ValueError):
            workflow.mark_no_show(stale, self.admin)

        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.ACTIVE)
        self.assertIsNotNone(reservation.checked_in_at)
        self.assertIsNone(reservation.no_show_marked_at)
        self.assertFalse(
            ReservationEvent.objects.filter(
                reservation=reservation,
                event_type=ReservationEvent.EventType.NO_SHOW,
            ).exists()
        )

    def test_no_show_wins_over_concurrent_check_in(self):
        """Once NO_SHOW is committed, a check-in request is refused."""
        reservation = self.make_reservation()
        stale = Reservation.objects.get(pk=reservation.pk)

        workflow.mark_no_show(reservation, self.admin)
        with self.assertRaises(ValueError):
            workflow.check_in_reservation(stale, self.requester)

        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.NO_SHOW)
        self.assertIsNone(reservation.checked_in_at)
        self.assertEqual(
            ReservationEvent.objects.filter(
                reservation=reservation,
                event_type=ReservationEvent.EventType.CHECKED_IN,
            ).count(),
            0,
        )

    def test_no_show_is_terminal_and_not_cancellable(self):
        reservation = self.make_reservation()
        self.mark_no_show(reservation)
        reservation.refresh_from_db()

        response = self.client.post(
            f"/api/reservations/{reservation.id}/cancel/",
            {"reason": "try again"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.NO_SHOW)

    # -- frontend contract -------------------------------------------------

    def test_staff_serializer_exposes_eligibility_for_ended_reservation(self):
        reservation = self.make_reservation()
        self.client.force_authenticate(self.admin)
        response = self.client.get(f"/api/reservations/{reservation.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["can_mark_no_show"])

    def test_serializer_disables_action_on_event_day(self):
        reservation = self.make_reservation(date=timezone.localdate())
        self.client.force_authenticate(self.admin)
        response = self.client.get(f"/api/reservations/{reservation.id}/")
        self.assertFalse(response.data["can_mark_no_show"])

    def test_requester_serializer_never_offers_admin_action(self):
        reservation = self.make_reservation()
        self.client.force_authenticate(self.requester)
        response = self.client.get(f"/api/reservations/{reservation.id}/")
        self.assertFalse(response.data["can_mark_no_show"])

    def test_status_counts_report_no_show_separately_from_rejected(self):
        reservation = self.make_reservation()
        self.mark_no_show(reservation)

        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/reservations/counts/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["NO_SHOW"], 1)
        self.assertEqual(response.data["REJECTED"], 0)

    def test_no_show_status_is_returned_after_refresh(self):
        reservation = self.make_reservation()
        self.mark_no_show(reservation)

        self.client.force_authenticate(self.admin)
        response = self.client.get(f"/api/reservations/{reservation.id}/")
        self.assertEqual(response.data["status"], Reservation.Status.NO_SHOW)
        self.assertEqual(response.data["status_label"], "No-show")
