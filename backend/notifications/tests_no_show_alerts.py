"""Tests for administrator possible-no-show alerts.

Covers the full chain: eligibility/stage calculation, persistence, deduplication,
escalation, resolution, the staff-only API, unread counts, authorization, and the
scheduled sweep command.
"""

from datetime import datetime, time, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from facilities.models import Facility
from notifications import no_show_alerts
from notifications.models import Notification, PossibleNoShowAlert
from reservations.models import Reservation
from reservations.services import workflow

User = get_user_model()


class AlertTestCase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="alert-admin",
            password="pass12345",
            role=User.Role.ADMIN,
        )
        self.requester = User.objects.create_user(
            username="alert-requester",
            password="pass12345",
            role=User.Role.REQUESTER,
            first_name="Maria",
            last_name="Santos",
            email="maria@campus.edu",
        )
        self.facility = Facility.objects.create(
            name="Alert Hall",
            facility_type=Facility.FacilityType.AVR,
            capacity=80,
        )
        self.day = timezone.localdate()
        self.client = APIClient()

    def make_reservation(self, **overrides):
        defaults = dict(
            requester=self.requester,
            requester_type=Reservation.RequesterType.CAMPUS,
            contact_email=self.requester.email,
            event_name="Leadership Summit",
            event_type=Reservation.EventType.SEMINAR,
            facility=self.facility,
            date=self.day,
            start_time=time(10, 0),
            end_time=time(12, 0),
            status=Reservation.Status.APPROVED,
            approved_at=timezone.make_aware(
                datetime.combine(self.day - timedelta(days=3), time(9, 0))
            ),
        )
        defaults.update(overrides)
        return Reservation.objects.create(**defaults)

    def at(self, hour, minute=0):
        """An aware datetime on the reservation's local day."""
        return timezone.make_aware(datetime.combine(self.day, time(hour, minute)))

    # -- stage calculation -------------------------------------------------

    def test_no_alert_outside_the_warning_window(self):
        reservation = self.make_reservation()
        summary = no_show_alerts.refresh_alerts(now=self.at(9, 44))

        self.assertEqual(summary["created"], 0)
        self.assertFalse(PossibleNoShowAlert.objects.exists())
        self.assertIsNone(no_show_alerts.stage_for(reservation, self.at(9, 44)))

    def test_upcoming_warning_fifteen_minutes_before_start(self):
        reservation = self.make_reservation()
        summary = no_show_alerts.refresh_alerts(now=self.at(9, 45))

        self.assertEqual(summary["created"], 1)
        alert = PossibleNoShowAlert.objects.get()
        self.assertEqual(alert.stage, PossibleNoShowAlert.Stage.UPCOMING)
        self.assertTrue(alert.is_unread)

    def test_start_time_reached_stage(self):
        self.make_reservation()
        no_show_alerts.refresh_alerts(now=self.at(10, 0))

        self.assertEqual(
            PossibleNoShowAlert.objects.get().stage,
            PossibleNoShowAlert.Stage.START_REACHED,
        )

    def test_action_required_fifteen_minutes_after_start(self):
        self.make_reservation()
        no_show_alerts.refresh_alerts(now=self.at(10, 15))

        self.assertEqual(
            PossibleNoShowAlert.objects.get().stage,
            PossibleNoShowAlert.Stage.NO_SHOW_RISK,
        )

    # -- exclusions --------------------------------------------------------

    def test_checked_in_reservation_is_excluded(self):
        reservation = self.make_reservation(checked_in_at=self.at(9, 55))
        no_show_alerts.refresh_alerts(now=self.at(10, 5))

        self.assertFalse(PossibleNoShowAlert.objects.exists())
        self.assertIsNone(no_show_alerts.stage_for(reservation, self.at(10, 5)))

    def test_ineligible_statuses_are_excluded(self):
        ineligible = [
            Reservation.Status.PENDING,
            Reservation.Status.ACTIVE,
            Reservation.Status.COMPLETED,
            Reservation.Status.REJECTED,
            Reservation.Status.CANCELLED,
            Reservation.Status.EXPIRED,
            Reservation.Status.NO_SHOW,
        ]
        for index, status in enumerate(ineligible):
            with self.subTest(status=status):
                PossibleNoShowAlert.objects.all().delete()
                Reservation.objects.all().delete()
                self.make_reservation(
                    event_name=f"Event {index}", status=status
                )
                no_show_alerts.refresh_alerts(now=self.at(10, 5))
                self.assertFalse(PossibleNoShowAlert.objects.exists())

    def test_event_that_already_ended_is_excluded(self):
        reservation = self.make_reservation()
        no_show_alerts.refresh_alerts(now=self.at(12, 1))
        self.assertFalse(PossibleNoShowAlert.objects.exists())
        self.assertFalse(no_show_alerts.is_eligible(reservation, self.at(12, 1)))

    # -- idempotency, escalation, resolution -------------------------------

    def test_repeated_runs_do_not_create_duplicates(self):
        self.make_reservation()

        no_show_alerts.refresh_alerts(now=self.at(9, 50))
        first = PossibleNoShowAlert.objects.get()
        no_show_alerts.refresh_alerts(now=self.at(9, 51))
        no_show_alerts.refresh_alerts(now=self.at(9, 52))

        self.assertEqual(PossibleNoShowAlert.objects.count(), 1)
        self.assertEqual(PossibleNoShowAlert.objects.get().pk, first.pk)

    def test_escalation_updates_stage_and_resets_acknowledgement(self):
        self.make_reservation()
        no_show_alerts.refresh_alerts(now=self.at(9, 50))
        alert = PossibleNoShowAlert.objects.get()
        no_show_alerts.acknowledge(alert, self.admin, now=self.at(9, 51))
        alert.refresh_from_db()
        self.assertTrue(alert.acknowledged_at)

        no_show_alerts.refresh_alerts(now=self.at(10, 0))
        alert.refresh_from_db()
        self.assertEqual(alert.stage, PossibleNoShowAlert.Stage.START_REACHED)
        self.assertIsNone(alert.acknowledged_at)
        self.assertTrue(alert.is_unread)

        no_show_alerts.acknowledge(alert, self.admin, now=self.at(10, 1))
        no_show_alerts.refresh_alerts(now=self.at(10, 20))
        alert.refresh_from_db()
        self.assertEqual(alert.stage, PossibleNoShowAlert.Stage.NO_SHOW_RISK)
        self.assertIsNone(alert.acknowledged_at)

    def test_alert_resolves_when_the_requester_checks_in(self):
        reservation = self.make_reservation()
        no_show_alerts.refresh_alerts(now=self.at(10, 5))
        self.assertTrue(PossibleNoShowAlert.objects.filter(resolved_at__isnull=True))

        reservation.status = Reservation.Status.ACTIVE
        reservation.checked_in_at = self.at(10, 6)
        reservation.save(update_fields=["status", "checked_in_at"])

        summary = no_show_alerts.refresh_alerts(now=self.at(10, 7))
        self.assertEqual(summary["resolved"], 1)
        alert = PossibleNoShowAlert.objects.get()
        self.assertIsNotNone(alert.resolved_at)
        self.assertEqual(alert.resolved_reason, "The requester checked in.")
        self.assertFalse(alert.is_unread)

    def test_alert_resolves_when_the_event_ends(self):
        self.make_reservation()
        no_show_alerts.refresh_alerts(now=self.at(10, 5))

        no_show_alerts.refresh_alerts(now=self.at(12, 5))
        alert = PossibleNoShowAlert.objects.get()
        self.assertIsNotNone(alert.resolved_at)
        self.assertEqual(alert.resolved_reason, "The event ended.")

    def test_alerts_for_cancelled_reservations_are_resolved(self):
        reservation = self.make_reservation()
        no_show_alerts.refresh_alerts(now=self.at(10, 5))

        reservation.status = Reservation.Status.CANCELLED
        reservation.save(update_fields=["status"])
        no_show_alerts.refresh_alerts(now=self.at(10, 6))

        self.assertEqual(
            PossibleNoShowAlert.objects.get().resolved_reason,
            "The reservation was cancelled.",
        )

    # -- SMTP independence -------------------------------------------------

    def test_smtp_failure_cannot_prevent_alert_persistence(self):
        self.make_reservation()
        boom = mock.Mock(side_effect=RuntimeError("SMTP host unreachable"))
        with mock.patch.object(EmailMultiAlternatives, "send", boom):
            summary = no_show_alerts.refresh_alerts(now=self.at(10, 5))

        self.assertEqual(summary["created"], 1)
        self.assertEqual(PossibleNoShowAlert.objects.count(), 1)
        self.assertEqual(mail.outbox, [])
        boom.assert_not_called()

    # -- API ---------------------------------------------------------------

    def _auth(self, user):
        self.client.force_authenticate(user)

    def _fixed_now(self, hour, minute=0):
        return self.at(hour, minute)

    def test_staff_api_returns_the_persisted_alert(self):
        reservation = self.make_reservation()
        self._auth(self.admin)

        with mock.patch(
            "notifications.no_show_alerts.timezone.now",
            return_value=self._fixed_now(9, 50),
        ):
            response = self.client.get("/api/notifications/no-show-alerts/")

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["unread"], 1)

        alert = body["results"][0]
        self.assertEqual(alert["reference"], reservation.reservation_id)
        self.assertEqual(alert["facility"], "Alert Hall")
        self.assertEqual(alert["requester"], "Maria Santos")
        self.assertEqual(alert["date"], reservation.date.isoformat())
        self.assertEqual(alert["start_time"], "10:00")
        self.assertEqual(alert["stage"], "UPCOMING")
        self.assertEqual(alert["time_label"], "Starts in 10 minutes")
        self.assertEqual(alert["no_check_in_label"], "No check-in recorded")
        self.assertEqual(alert["link"], f"/reservations/{reservation.pk}")
        self.assertFalse(alert["acknowledged"])

    def test_admin_notification_feed_combines_events_and_alerts_unread_first(self):
        reservation = self.make_reservation()
        old_unread = Notification.objects.create(
            user=self.admin,
            title="Reservation submitted",
            message="Awaiting review",
            link="/reservations/100",
        )
        read_notice = Notification.objects.create(
            user=self.admin,
            title="Older reservation update",
            read=True,
            link="/reservations/101",
        )
        current = self._fixed_now(9, 50)
        Notification.objects.filter(pk=old_unread.pk).update(
            created_at=current - timedelta(minutes=5)
        )
        Notification.objects.filter(pk=read_notice.pk).update(
            created_at=current - timedelta(hours=2)
        )
        self._auth(self.admin)

        with mock.patch(
            "notifications.no_show_alerts.timezone.now",
            return_value=self._fixed_now(9, 50),
        ):
            response = self.client.get("/api/notifications/")

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["count"], 3)
        self.assertEqual(
            [row["source"] for row in body["results"]],
            ["possible_no_show", "notification", "notification"],
        )
        self.assertEqual([row["read"] for row in body["results"]], [False, False, True])
        self.assertEqual(body["results"][0]["stage"], "UPCOMING")
        self.assertEqual(body["results"][0]["link"], f"/reservations/{reservation.pk}")
        self.assertEqual(body["results"][1]["title"], "Reservation submitted")

    def test_mark_all_read_updates_workflow_notifications_and_alerts(self):
        self.make_reservation()
        notification = Notification.objects.create(
            user=self.admin, title="Reservation submitted"
        )
        self._auth(self.admin)
        with mock.patch(
            "notifications.no_show_alerts.timezone.now",
            return_value=self._fixed_now(9, 50),
        ):
            self.client.get("/api/notifications/")

        response = self.client.post("/api/notifications/mark_all_read/")
        self.assertEqual(response.status_code, 200, response.content)
        notification.refresh_from_db()
        self.assertTrue(notification.read)
        self.assertIsNotNone(PossibleNoShowAlert.objects.get().acknowledged_at)

    def test_requester_feed_does_not_include_staff_notifications_or_alerts(self):
        self.make_reservation()
        Notification.objects.create(user=self.admin, title="Staff only")
        no_show_alerts.refresh_alerts(now=self.at(9, 50))
        self._auth(self.requester)

        response = self.client.get("/api/notifications/")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["count"], 0)
        self.assertEqual(response.json()["results"], [])

    def test_approval_creates_a_staff_notification_for_other_admins(self):
        colleague = User.objects.create_user(
            username="alert-colleague",
            password="pass12345",
            role=User.Role.STAFF,
        )
        reservation = self.make_reservation(
            status=Reservation.Status.PENDING,
            date=self.day + timedelta(days=3),
        )
        with mock.patch("reservations.services.workflow._schedule_approval_email"):
            workflow.approve_reservation(reservation, self.admin)

        notice = Notification.objects.get(
            user=colleague,
            title="Reservation approved",
            link=f"/reservations/{reservation.pk}",
        )
        self.assertIn(reservation.event_name, notice.message)
        self.assertFalse(
            Notification.objects.filter(
                user=self.admin, title="Reservation approved"
            ).exists()
        )

    def test_unread_count_includes_alerts_for_staff_only(self):
        self.make_reservation()
        Notification.objects.create(
            user=self.admin, title="Existing unread notification"
        )

        with mock.patch(
            "notifications.no_show_alerts.timezone.now",
            return_value=self._fixed_now(9, 50),
        ):
            self._auth(self.admin)
            staff_body = self.client.get("/api/notifications/unread_count/").json()

        self.assertEqual(staff_body["count"], 2)
        self.assertEqual(staff_body["notifications"], 1)
        self.assertEqual(staff_body["alerts"], 1)

        self._auth(self.requester)
        requester_body = self.client.get("/api/notifications/unread_count/").json()
        self.assertEqual(requester_body["count"], 0)
        self.assertEqual(requester_body["alerts"], 0)

    def test_acknowledging_an_alert_clears_its_unread_state(self):
        self.make_reservation()
        self._auth(self.admin)
        with mock.patch(
            "notifications.no_show_alerts.timezone.now",
            return_value=self._fixed_now(9, 50),
        ):
            listed = self.client.get("/api/notifications/no-show-alerts/").json()
        alert_id = listed["results"][0]["id"]

        response = self.client.post(
            f"/api/notifications/no-show-alerts/{alert_id}/acknowledge/"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["acknowledged"])

        alert = PossibleNoShowAlert.objects.get(pk=alert_id)
        self.assertEqual(alert.acknowledged_by, self.admin)
        self.assertEqual(no_show_alerts.unread_count(), 0)

    def test_acknowledge_all_marks_every_active_alert_read(self):
        self.make_reservation(event_name="Morning", start_time=time(10, 0))
        self.make_reservation(event_name="Second", start_time=time(10, 10))
        self._auth(self.admin)
        with mock.patch(
            "notifications.no_show_alerts.timezone.now",
            return_value=self._fixed_now(10, 0),
        ):
            self.client.get("/api/notifications/no-show-alerts/")

        response = self.client.post(
            "/api/notifications/no-show-alerts/acknowledge-all/"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["acknowledged"], 2)
        self.assertEqual(no_show_alerts.unread_count(), 0)

    def test_regular_users_cannot_reach_administrator_alerts(self):
        self.make_reservation()
        no_show_alerts.refresh_alerts(now=self.at(10, 5))
        alert = PossibleNoShowAlert.objects.get()
        self._auth(self.requester)

        for method, url in [
            ("get", "/api/notifications/no-show-alerts/"),
            ("post", f"/api/notifications/no-show-alerts/{alert.pk}/acknowledge/"),
            ("post", "/api/notifications/no-show-alerts/acknowledge-all/"),
        ]:
            with self.subTest(url=url):
                response = getattr(self.client, method)(url)
                self.assertEqual(response.status_code, 403, response.content)

        alert.refresh_from_db()
        self.assertIsNone(alert.acknowledged_at)

    def test_anonymous_users_are_rejected(self):
        self.client.force_authenticate(None)
        response = self.client.get("/api/notifications/no-show-alerts/")
        self.assertIn(response.status_code, (401, 403))

    def test_alerts_show_the_most_urgent_first(self):
        self.make_reservation(event_name="Upcoming", start_time=time(10, 10))
        self.make_reservation(event_name="Late", start_time=time(9, 30))
        self._auth(self.admin)
        with mock.patch(
            "notifications.no_show_alerts.timezone.now",
            return_value=self._fixed_now(10, 0),
        ):
            body = self.client.get("/api/notifications/no-show-alerts/").json()

        self.assertEqual([row["stage"] for row in body["results"]], [
            "NO_SHOW_RISK",
            "UPCOMING",
        ])

    # -- management command ------------------------------------------------

    def test_management_command_is_idempotent(self):
        self.make_reservation()
        with mock.patch(
            "notifications.no_show_alerts.timezone.now",
            return_value=self._fixed_now(10, 5),
        ):
            call_command("process_reservation_notifications", verbosity=0)
            call_command("process_reservation_notifications", verbosity=0)

        self.assertEqual(PossibleNoShowAlert.objects.count(), 1)
        self.assertEqual(
            PossibleNoShowAlert.objects.get().stage,
            PossibleNoShowAlert.Stage.START_REACHED,
        )


class AwaitingNoShowReviewTests(AlertTestCase):
    """Overdue reservations that still require an explicit administrator review."""

    def setUp(self):
        super().setUp()
        self.yesterday = self.day - timedelta(days=1)

    def make_overdue(self, **overrides):
        defaults = dict(
            date=self.yesterday,
            start_time=time(10, 0),
            end_time=time(12, 0),
        )
        defaults.update(overrides)
        return self.make_reservation(**defaults)

    def list_alerts(self, hour, minute=0, user=None):
        self._auth(user or self.admin)
        fixed = self._fixed_now(hour, minute)
        with mock.patch(
            "notifications.no_show_alerts.timezone.now", return_value=fixed
        ), mock.patch(
            "reservations.services.workflow.timezone.now", return_value=fixed
        ):
            response = self.client.get("/api/notifications/no-show-alerts/")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_overdue_reservation_is_listed_for_review(self):
        reservation = self.make_overdue()

        body = self.list_alerts(10, 0)

        self.assertEqual(body["count"], 0)
        self.assertEqual(body["results"], [])
        self.assertEqual(body["review_count"], 1)
        row = body["awaiting_review"][0]
        self.assertEqual(row["reservation"], reservation.pk)
        self.assertEqual(row["reference"], reservation.reservation_id)
        self.assertEqual(row["event_name"], "Leadership Summit")
        self.assertEqual(row["facility"], "Alert Hall")
        self.assertEqual(row["requester"], "Maria Santos")
        self.assertEqual(row["date"], self.yesterday.isoformat())
        self.assertEqual(row["start_time"], "10:00")
        self.assertEqual(row["end_time"], "12:00")
        self.assertEqual(row["status"], Reservation.Status.APPROVED)
        self.assertEqual(row["link"], f"/reservations/{reservation.pk}")
        self.assertEqual(row["time_label"], "Ended 22 hours ago")
        self.assertEqual(row["no_check_in_label"], "No check-in recorded")
        self.assertTrue(row["can_mark_no_show"])

    def test_possible_no_show_is_not_duplicated_in_review(self):
        reservation = self.make_reservation()

        body = self.list_alerts(10, 5)

        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["reservation"], reservation.pk)
        self.assertEqual(body["review_count"], 0)
        self.assertEqual(body["awaiting_review"], [])

    def test_reservation_with_an_active_alert_is_deduplicated_by_id(self):
        reservation = self.make_overdue()
        PossibleNoShowAlert.objects.create(
            reservation=reservation,
            stage=PossibleNoShowAlert.Stage.NO_SHOW_RISK,
            detected_at=self.at(10, 20),
            stage_changed_at=self.at(10, 20),
        )

        review_ids = [
            row.pk
            for row in no_show_alerts.awaiting_review(now=self._fixed_now(10, 30))
        ]
        self.assertNotIn(reservation.pk, review_ids)

        # The next sweep resolves the stale (ended) alert, so the reservation is
        # then listed exactly once — in the review group, never in both.
        body = self.list_alerts(10, 30)
        self.assertEqual(body["count"], 0)
        self.assertEqual(body["review_count"], 1)
        self.assertEqual(body["awaiting_review"][0]["reservation"], reservation.pk)

    def test_future_reservation_is_excluded(self):
        self.make_overdue(date=self.day + timedelta(days=2))

        body = self.list_alerts(10, 0)

        self.assertEqual(body["review_count"], 0)
        self.assertEqual(body["awaiting_review"], [])

    def test_today_reservation_whose_end_time_has_not_passed_is_excluded(self):
        self.make_reservation(start_time=time(14, 0), end_time=time(16, 0))

        body = self.list_alerts(15, 0)

        self.assertEqual(body["review_count"], 0)

    def test_today_reservation_whose_end_time_has_passed_is_listed(self):
        reservation = self.make_reservation(start_time=time(10, 0), end_time=time(12, 0))

        body = self.list_alerts(12, 5)

        self.assertEqual(body["review_count"], 1)
        self.assertEqual(body["awaiting_review"][0]["reservation"], reservation.pk)
        self.assertEqual(body["awaiting_review"][0]["time_label"], "Ended 5 minutes ago")
        # The existing no-show rule only allows marking from the NEXT local day.
        self.assertFalse(body["awaiting_review"][0]["can_mark_no_show"])

    def test_checked_in_reservation_is_excluded(self):
        self.make_overdue(
            status=Reservation.Status.ACTIVE,
            checked_in_at=self.at(10, 5),
        )
        self.make_overdue(
            event_name="Checked in but still approved",
            checked_in_at=self.at(10, 5),
        )

        body = self.list_alerts(13, 0)

        self.assertEqual(body["review_count"], 0)

    def test_completed_reservation_is_excluded(self):
        self.make_overdue(status=Reservation.Status.COMPLETED)

        body = self.list_alerts(13, 0)

        self.assertEqual(body["review_count"], 0)

    def test_cancelled_reservation_is_excluded(self):
        self.make_overdue(status=Reservation.Status.CANCELLED)

        body = self.list_alerts(13, 0)

        self.assertEqual(body["review_count"], 0)

    def test_confirmed_no_show_is_excluded(self):
        self.make_overdue(
            status=Reservation.Status.NO_SHOW,
            no_show_marked_at=self.at(9, 0),
            no_show_marked_by=self.admin,
        )

        body = self.list_alerts(13, 0)

        self.assertEqual(body["review_count"], 0)

    def test_review_is_only_visible_to_administrators(self):
        self.make_overdue()

        self._auth(self.requester)
        response = self.client.get("/api/notifications/no-show-alerts/")

        self.assertEqual(response.status_code, 403, response.content)
