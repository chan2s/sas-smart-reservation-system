"""Tests for the automatic three-days-before reservation reminder.

Covers the scheduling rules (only approved reservations; exactly three calendar
days before the event, or promptly for late approvals; never after the event
started or for reservations approved on/after the event date), the single
delivery guarantee across repeated/concurrent runs, timezone handling, retry
after a notification failure, and the cron management command.
"""

from datetime import datetime, time, timedelta, timezone as datetime_timezone
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from facilities.models import Facility
from notifications.models import Notification
from reservations.models import Reservation, ReservationEvent
from reservations.services import reminders

User = get_user_model()


class ReminderTestCase(TestCase):
    def setUp(self):
        self.requester = User.objects.create_user(
            username="reminder-requester",
            password="pass12345",
            role=User.Role.REQUESTER,
            email="requester@campus.edu",
        )
        self.facility = Facility.objects.create(
            name="Reminder Hall",
            facility_type=Facility.FacilityType.AVR,
            capacity=80,
        )
        self.today = timezone.localdate()

    def make_reservation(self, **overrides):
        defaults = dict(
            requester=self.requester,
            requester_type=Reservation.RequesterType.CAMPUS,
            contact_email=self.requester.email,
            event_name="Science Fair",
            event_type=Reservation.EventType.ACADEMIC,
            facility=self.facility,
            date=self.today + timedelta(days=3),
            start_time=time(9, 0),
            end_time=time(11, 0),
            status=Reservation.Status.APPROVED,
            approved_at=timezone.make_aware(
                datetime.combine(self.today - timedelta(days=7), time(9, 0))
            ),
        )
        defaults.update(overrides)
        return Reservation.objects.create(**defaults)

    def now_before_event(self, reservation):
        """A safe "now" shortly before the reservation starts."""
        return reservation.start_datetime - timedelta(hours=1)

    # -- eligibility -------------------------------------------------------

    def test_approved_reservation_gets_reminder_three_days_before(self):
        reservation = self.make_reservation()
        result = reminders.send_due_reminders(now=self.now_before_event(reservation))

        self.assertEqual(result["sent"], 1)
        reservation.refresh_from_db()
        self.assertIsNotNone(reservation.reminder_sent_at)
        notification = Notification.objects.get(user=self.requester)
        self.assertEqual(notification.title, reminders.REMINDER_TITLE)
        self.assertIn(reservation.reservation_id, notification.message)
        self.assertIn("Science Fair", notification.message)
        self.assertIn("Reminder Hall", notification.message)
        self.assertIn("9:00 AM", notification.message)
        self.assertIn("11:00 AM", notification.message)
        self.assertIn(
            "Please remember to attend your scheduled reservation.",
            notification.message,
        )
        self.assertEqual(notification.link, f"/reservations/{reservation.id}")
        self.assertTrue(
            ReservationEvent.objects.filter(
                reservation=reservation,
                event_type=ReservationEvent.EventType.REMINDER_SENT,
            ).exists()
        )

    def test_pending_reservation_does_not_get_reminder(self):
        reservation = self.make_reservation(status=Reservation.Status.PENDING)
        reminders.send_due_reminders(now=self.now_before_event(reservation))
        self.assertFalse(Notification.objects.exists())

    def test_rejected_reservation_does_not_get_reminder(self):
        reservation = self.make_reservation(status=Reservation.Status.REJECTED)
        reminders.send_due_reminders(now=self.now_before_event(reservation))
        self.assertFalse(Notification.objects.exists())

    def test_cancelled_reservation_does_not_get_reminder(self):
        reservation = self.make_reservation(status=Reservation.Status.CANCELLED)
        reminders.send_due_reminders(now=self.now_before_event(reservation))
        self.assertFalse(Notification.objects.exists())

    def test_cancelled_between_scan_and_send_is_skipped(self):
        """A status change after the sweep scanned the row still suppresses it."""
        reservation = self.make_reservation()
        stale = Reservation.objects.get(pk=reservation.pk)
        Reservation.objects.filter(pk=reservation.pk).update(
            status=Reservation.Status.CANCELLED
        )

        sent = reminders._send_reminder(stale, self.now_before_event(reservation))

        self.assertFalse(sent)
        self.assertFalse(Notification.objects.exists())
        stale.refresh_from_db()
        self.assertIsNone(stale.reminder_sent_at)

    def test_reservation_beyond_three_day_window_is_not_reminded_yet(self):
        reservation = self.make_reservation(date=self.today + timedelta(days=4))
        now = timezone.make_aware(datetime.combine(self.today, time(12, 0)))
        reminders.send_due_reminders(now=now)
        self.assertFalse(Notification.objects.exists())

    def test_each_reservation_is_reminded_only_once(self):
        reservation = self.make_reservation()
        now = self.now_before_event(reservation)

        first = reminders.send_due_reminders(now=now)
        second = reminders.send_due_reminders(now=now + timedelta(minutes=5))

        self.assertEqual(first["sent"], 1)
        self.assertEqual(second["sent"], 0)
        self.assertEqual(
            Notification.objects.filter(user=self.requester).count(), 1
        )
        self.assertEqual(
            ReservationEvent.objects.filter(
                reservation=reservation,
                event_type=ReservationEvent.EventType.REMINDER_SENT,
            ).count(),
            1,
        )

    def test_late_approval_inside_three_days_is_reminded_promptly(self):
        reservation = self.make_reservation(
            date=self.today + timedelta(days=1),
            approved_at=timezone.make_aware(
                datetime.combine(self.today, time(8, 0))
            ),
        )
        result = reminders.send_due_reminders(now=self.now_before_event(reservation))
        self.assertEqual(result["sent"], 1)
        self.assertTrue(Notification.objects.exists())

    def test_reservation_approved_on_event_date_is_not_reminded(self):
        event_date = self.today + timedelta(days=2)
        reservation = self.make_reservation(
            date=event_date,
            approved_at=timezone.make_aware(
                datetime.combine(event_date, time(8, 0))
            ),
        )
        reminders.send_due_reminders(now=self.now_before_event(reservation))
        self.assertFalse(Notification.objects.exists())

    def test_reservation_approved_after_event_date_is_not_reminded(self):
        reservation = self.make_reservation(
            date=self.today + timedelta(days=1),
            approved_at=timezone.make_aware(
                datetime.combine(self.today + timedelta(days=2), time(8, 0))
            ),
        )
        reminders.send_due_reminders(now=self.now_before_event(reservation))
        self.assertFalse(Notification.objects.exists())

    def test_event_already_started_is_not_reminded(self):
        reservation = self.make_reservation(
            date=self.today,
            start_time=time(9, 0),
            end_time=time(11, 0),
            approved_at=timezone.make_aware(
                datetime.combine(self.today - timedelta(days=1), time(9, 0))
            ),
        )
        started = timezone.make_aware(datetime.combine(self.today, time(10, 0)))
        reminders.send_due_reminders(now=started)
        self.assertFalse(Notification.objects.exists())

    def test_requester_without_account_is_skipped_without_error(self):
        reservation = self.make_reservation(
            requester=None,
            requester_type=Reservation.RequesterType.EXTERNAL,
            organization="Community Group",
            contact_email="group@example.com",
        )
        result = reminders.send_due_reminders(now=self.now_before_event(reservation))
        self.assertEqual(result["sent"], 0)
        self.assertFalse(Notification.objects.exists())

    def test_reminder_uses_local_calendar_date_across_midnight(self):
        """A 00:30 event three local days out is due on the local calendar day."""
        reservation = self.make_reservation(
            date=self.today + timedelta(days=3),
            start_time=time(0, 30),
            end_time=time(2, 30),
        )
        late_evening = timezone.make_aware(
            datetime.combine(self.today, time(23, 45))
        )
        reminders.send_due_reminders(now=late_evening)
        reservation.refresh_from_db()
        self.assertIsNotNone(reservation.reminder_sent_at)
        self.assertEqual(
            timezone.localdate(reservation.reminder_sent_at), self.today
        )

    def test_due_date_uses_local_timezone_not_utc(self):
        """00:30 Manila on the due day is still the previous UTC day."""
        reservation = self.make_reservation(date=self.today + timedelta(days=3))
        # 16:30 UTC == 00:30 Asia/Manila the NEXT calendar day.
        just_after_local_midnight = datetime.combine(
            self.today - timedelta(days=1),
            time(16, 30),
            tzinfo=datetime_timezone.utc,
        )

        result = reminders.send_due_reminders(now=just_after_local_midnight)

        self.assertEqual(result["sent"], 1)
        self.assertTrue(Notification.objects.exists())

    # -- failure / retry ---------------------------------------------------

    def test_notification_failure_is_logged_and_retried(self):
        reservation = self.make_reservation()
        now = self.now_before_event(reservation)

        with mock.patch(
            "reservations.services.reminders.notify",
            side_effect=RuntimeError("notification store unavailable"),
        ):
            with self.assertLogs("reservations.services.reminders", "ERROR"):
                result = reminders.send_due_reminders(now=now)

        self.assertEqual(result["failed"], 1)
        reservation.refresh_from_db()
        self.assertIsNone(reservation.reminder_sent_at)
        self.assertFalse(Notification.objects.exists())

        retried = reminders.send_due_reminders(now=now)
        self.assertEqual(retried["sent"], 1)
        reservation.refresh_from_db()
        self.assertIsNotNone(reservation.reminder_sent_at)

    # -- scheduler ---------------------------------------------------------

    def test_management_command_sends_due_reminders(self):
        self.make_reservation()
        call_command("send_reservation_reminders", stdout=mock.Mock())
        self.assertEqual(
            Notification.objects.filter(user=self.requester).count(), 1
        )

    def test_management_command_dry_run_sends_nothing(self):
        self.make_reservation()
        call_command(
            "send_reservation_reminders", "--dry-run", stdout=mock.Mock()
        )
        self.assertFalse(Notification.objects.exists())
