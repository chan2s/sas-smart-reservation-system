"""Tests for the automatic three-days-before reservation reminder.

Covers the scheduling rules (only approved reservations; three calendar days
before the event, or promptly for late approvals; never after the event
started), email content, email failure/retry, the single-delivery guarantee
across repeated/stale/concurrent checks, restart persistence, timezone
handling, the cron management command, and scheduler leader election.
"""

from datetime import datetime, time, timedelta, timezone as datetime_timezone
from unittest import mock
import os

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from equipment.models import Equipment, EquipmentCategory
from facilities.models import Facility
from notifications.models import Notification
from reservations import scheduler
from reservations.models import (
    Reservation,
    ReservationEvent,
    ReservationItem,
)
from reservations.services import reminders

User = get_user_model()


class ReminderTestCase(TestCase):
    def setUp(self):
        self.requester = User.objects.create_user(
            username="reminder-requester",
            password="pass12345",
            role=User.Role.REQUESTER,
            email="requester@campus.edu",
            first_name="Maria",
            last_name="Santos",
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

    def test_approved_reservation_gets_branded_email_with_full_details(self):
        category = EquipmentCategory.objects.create(name="Audio Visual")
        projector = Equipment.objects.create(
            name="Projector", category=category, total_quantity=10
        )
        reservation = self.make_reservation()
        ReservationItem.objects.create(
            reservation=reservation, equipment=projector, quantity=2
        )

        result = reminders.send_due_reminders(now=self.now_before_event(reservation))

        self.assertEqual(result["emails_sent"], 1)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(
            message.subject,
            "Check-In Reminder - SAS RESERVE",
        )
        self.assertEqual(message.to, [self.requester.email])
        self.assertIn("Maria Santos", message.body)
        self.assertIn(reservation.reservation_id, message.body)
        self.assertIn("Science Fair", message.body)
        self.assertIn("Reminder Hall", message.body)
        self.assertIn("2x Projector", message.body)
        self.assertIn("9:00 AM", message.body)
        self.assertIn("11:00 AM", message.body)
        self.assertIn("within the next three days", message.body)
        self.assertIn("3 hours before", message.body)
        self.assertIn("SAS RESERVE", message.body)

        html = message.alternatives[0][0]
        self.assertIn("SAS RESERVE", html)
        self.assertIn("Reminder Hall", html)
        self.assertIn("2x Projector", html)

        reservation.refresh_from_db()
        self.assertIsNotNone(reservation.reminder_email_sent_at)
        self.assertIsNone(reservation.reminder_email_claimed_at)

    def test_pending_reservation_does_not_get_reminder(self):
        reservation = self.make_reservation(status=Reservation.Status.PENDING)
        reminders.send_due_reminders(now=self.now_before_event(reservation))
        self.assertFalse(Notification.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_rejected_reservation_does_not_get_reminder(self):
        reservation = self.make_reservation(status=Reservation.Status.REJECTED)
        reminders.send_due_reminders(now=self.now_before_event(reservation))
        self.assertFalse(Notification.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_cancelled_reservation_does_not_get_reminder(self):
        reservation = self.make_reservation(status=Reservation.Status.CANCELLED)
        reminders.send_due_reminders(now=self.now_before_event(reservation))
        self.assertFalse(Notification.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_no_show_reservation_does_not_get_reminder(self):
        reservation = self.make_reservation(status=Reservation.Status.NO_SHOW)
        reminders.send_due_reminders(now=self.now_before_event(reservation))
        self.assertFalse(Notification.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

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
        self.assertEqual(len(mail.outbox), 0)
        stale.refresh_from_db()
        self.assertIsNone(stale.reminder_sent_at)
        self.assertIsNone(stale.reminder_email_sent_at)

    def test_reservation_beyond_three_day_window_is_not_reminded_yet(self):
        reservation = self.make_reservation(date=self.today + timedelta(days=4))
        now = timezone.make_aware(datetime.combine(self.today, time(12, 0)))
        reminders.send_due_reminders(now=now)
        self.assertFalse(Notification.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

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
        self.assertEqual(len(mail.outbox), 1)

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
        self.assertEqual(len(mail.outbox), 0)

    def test_reservation_approved_after_event_date_is_not_reminded(self):
        reservation = self.make_reservation(
            date=self.today + timedelta(days=1),
            approved_at=timezone.make_aware(
                datetime.combine(self.today + timedelta(days=2), time(8, 0))
            ),
        )
        reminders.send_due_reminders(now=self.now_before_event(reservation))
        self.assertFalse(Notification.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

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
        self.assertEqual(len(mail.outbox), 0)

    def test_requester_without_account_uses_contact_email_for_email_only(self):
        reservation = self.make_reservation(
            requester=None,
            requester_type=Reservation.RequesterType.EXTERNAL,
            organization="Community Group",
            contact_email="group@example.com",
        )
        result = reminders.send_due_reminders(now=self.now_before_event(reservation))

        self.assertEqual(result["sent"], 1)
        self.assertEqual(result["emails_sent"], 1)
        self.assertFalse(Notification.objects.exists())
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["group@example.com"])
        reservation.refresh_from_db()
        self.assertIsNone(reservation.reminder_sent_at)
        self.assertIsNotNone(reservation.reminder_email_sent_at)

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
        self.assertEqual(len(mail.outbox), 1)

    # -- duplicate prevention / restart -----------------------------------

    def test_each_reservation_is_reminded_only_once(self):
        reservation = self.make_reservation()
        now = self.now_before_event(reservation)

        first = reminders.send_due_reminders(now=now)
        second = reminders.send_due_reminders(now=now + timedelta(minutes=5))
        third = reminders.send_due_reminders(now=now + timedelta(hours=1))

        self.assertEqual(first["sent"], 1)
        self.assertEqual(first["emails_sent"], 1)
        self.assertEqual(second["sent"], 0)
        self.assertEqual(second["emails_sent"], 0)
        self.assertEqual(third["emails_sent"], 0)
        self.assertEqual(len(mail.outbox), 1)
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

    def test_restart_does_not_reset_reminder_history(self):
        """A fresh process reads the persisted marker and sends nothing."""
        reservation = self.make_reservation()
        now = self.now_before_event(reservation)
        reminders.send_due_reminders(now=now)
        self.assertEqual(len(mail.outbox), 1)

        # Simulate a backend restart: drop the in-memory instance and rebuild
        # it from the database, exactly as a new process would.
        reservation_pk = reservation.pk
        del reservation
        reloaded = Reservation.objects.get(pk=reservation_pk)
        self.assertIsNotNone(reloaded.reminder_email_sent_at)

        result = reminders.send_due_reminders(now=now + timedelta(hours=1))

        self.assertEqual(result["emails_sent"], 0)
        self.assertEqual(result["already_sent"], 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_stale_concurrent_checkers_do_not_duplicate_email(self):
        """Two workers that scanned the same row both run; only one sends."""
        reservation = self.make_reservation()
        now = self.now_before_event(reservation)
        first_worker = Reservation.objects.get(pk=reservation.pk)
        second_worker = Reservation.objects.get(pk=reservation.pk)

        first = reminders._process_reminder(first_worker, now)
        second = reminders._process_reminder(second_worker, now)

        self.assertTrue(first["delivered"])
        self.assertFalse(second["delivered"])
        self.assertEqual(second["email_result"], "skipped")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            Notification.objects.filter(user=self.requester).count(), 1
        )

    def test_email_claim_is_exclusive_and_released_on_failure(self):
        reservation = self.make_reservation()
        now = self.now_before_event(reservation)

        self.assertTrue(reminders._claim_email(reservation, now))
        self.assertFalse(
            reminders._claim_email(reservation, now + timedelta(seconds=1))
        )

        reminders._release_email_claim(reservation, now)
        self.assertTrue(
            reminders._claim_email(reservation, now + timedelta(seconds=2))
        )

    # -- failure / retry -------------------------------------------------

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
        # The email channel is independent and already succeeded.
        self.assertIsNotNone(reservation.reminder_email_sent_at)
        self.assertFalse(Notification.objects.exists())

        retried = reminders.send_due_reminders(now=now)
        self.assertEqual(retried["sent"], 1)
        reservation.refresh_from_db()
        self.assertIsNotNone(reservation.reminder_sent_at)
        # No duplicate email on the in-app retry.
        self.assertEqual(len(mail.outbox), 1)

    def test_email_failure_is_retried_on_a_later_check(self):
        reservation = self.make_reservation()
        now = self.now_before_event(reservation)

        with mock.patch(
            "reservations.services.reminders.send_reservation_reminder",
            return_value=(False, "smtp"),
        ):
            with self.assertLogs("reservations.services.reminders", "ERROR"):
                result = reminders.send_due_reminders(now=now)

        self.assertEqual(result["emails_failed"], 1)
        self.assertEqual(len(mail.outbox), 0)
        reservation.refresh_from_db()
        self.assertIsNone(reservation.reminder_email_sent_at)
        self.assertIsNone(reservation.reminder_email_claimed_at)

        retried = reminders.send_due_reminders(now=now + timedelta(minutes=5))

        self.assertEqual(retried["emails_sent"], 1)
        self.assertEqual(len(mail.outbox), 1)
        reservation.refresh_from_db()
        self.assertIsNotNone(reservation.reminder_email_sent_at)

    def test_requester_with_no_valid_email_is_handled_safely(self):
        requester = User.objects.create_user(
            username="no-email-user",
            password="pass12345",
            role=User.Role.REQUESTER,
            email="",
        )
        reservation = self.make_reservation(
            requester=requester,
            contact_email="",
        )

        result = reminders.send_due_reminders(now=self.now_before_event(reservation))

        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(result["emails_skipped"], 1)
        self.assertEqual(result["failed"], 0)
        reservation.refresh_from_db()
        self.assertIsNone(reservation.reminder_email_sent_at)
        # The in-app reminder still reaches the account holder.
        self.assertIsNotNone(reservation.reminder_sent_at)
        self.assertTrue(Notification.objects.filter(user=requester).exists())

    def test_multiple_eligible_reservations_are_all_reminded(self):
        first = self.make_reservation(event_name="Morning Forum")
        second = self.make_reservation(
            event_name="Afternoon Workshop", start_time=time(14, 0), end_time=time(16, 0)
        )

        result = reminders.send_due_reminders(now=self.now_before_event(first))

        self.assertEqual(result["scanned"], 2)
        self.assertEqual(result["sent"], 2)
        self.assertEqual(result["emails_sent"], 2)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(
            {message.to[0] for message in mail.outbox},
            {self.requester.email},
        )
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertIsNotNone(first.reminder_email_sent_at)
        self.assertIsNotNone(second.reminder_email_sent_at)

    # -- scheduler --------------------------------------------------------

    def test_management_command_sends_due_reminders(self):
        self.make_reservation()
        call_command("send_reservation_reminders", stdout=mock.Mock())
        self.assertEqual(
            Notification.objects.filter(user=self.requester).count(), 1
        )
        self.assertEqual(len(mail.outbox), 1)

    def test_management_command_dry_run_sends_nothing(self):
        self.make_reservation()
        call_command(
            "send_reservation_reminders", "--dry-run", stdout=mock.Mock()
        )
        self.assertFalse(Notification.objects.exists())
        self.assertEqual(len(mail.outbox), 0)


class ReminderSchedulerTests(TestCase):
    def test_scheduler_starts_for_a_wsgi_server(self):
        self.assertTrue(
            scheduler.should_start_scheduler(["gunicorn", "config.wsgi:application"])
        )

    def test_scheduler_does_not_start_for_management_commands(self):
        for command in (
            "migrate",
            "makemigrations",
            "test",
            "collectstatic",
            "shell",
            "expire_reservations",
            "send_reservation_reminders",
            "run_reminder_scheduler",
        ):
            with self.subTest(command=command):
                self.assertFalse(
                    scheduler.should_start_scheduler(["manage.py", command])
                )

    def test_scheduler_skips_runserver_autoreload_parent(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RUN_MAIN", None)
            self.assertFalse(
                scheduler.should_start_scheduler(["manage.py", "runserver"])
            )

    def test_scheduler_starts_in_runserver_child_or_noreload(self):
        with mock.patch.dict(os.environ, {"RUN_MAIN": "true"}):
            self.assertTrue(
                scheduler.should_start_scheduler(["manage.py", "runserver"])
            )
        self.assertTrue(
            scheduler.should_start_scheduler(
                ["manage.py", "runserver", "--noreload"]
            )
        )

    @override_settings(REMINDER_SCHEDULER_ENABLED=False)
    def test_scheduler_can_be_disabled_by_environment_setting(self):
        self.assertFalse(
            scheduler.should_start_scheduler(["gunicorn", "config.wsgi:application"])
        )

    def test_database_lease_elects_exactly_one_scheduler(self):
        now = timezone.now()

        self.assertTrue(scheduler.acquire_lease("worker-a", now=now))
        self.assertFalse(scheduler.acquire_lease("worker-b", now=now))
        self.assertTrue(scheduler.renew_lease("worker-a", now=now))
        self.assertFalse(scheduler.renew_lease("worker-b", now=now))

        # After the lease expires, another worker can take over.
        later = now + timedelta(hours=1)
        self.assertTrue(scheduler.acquire_lease("worker-b", now=later))
        self.assertFalse(scheduler.renew_lease("worker-a", now=later))
