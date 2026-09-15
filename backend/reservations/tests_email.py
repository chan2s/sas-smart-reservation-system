"""Tests for the approval-reservation email notification workflow.

The email is only dispatched after the approval transaction commits
(``transaction.on_commit``), is guarded against double-sends, never affects
the approval itself on failure, and its delivery state is tracked on the
``Reservation.approval_email_status`` field.
"""

from datetime import date, time

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.utils import timezone

from facilities.models import Facility, OperatingHour
from reservations.models import Reservation
from reservations.services import workflow

User = get_user_model()


class ApprovalEmailFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username="approver", password="pass12345", role=User.Role.ADMIN
        )
        cls.requester = User.objects.create_user(
            username="requestor",
            password="pass12345",
            role=User.Role.REQUESTER,
            first_name="Juan",
            last_name="Dela Cruz",
            email="juan@campus.edu",
        )
        cls.facility = Facility.objects.create(
            name="Email Test AVR", facility_type=Facility.FacilityType.AVR, capacity=50
        )
        OperatingHour.objects.create(
            facility=cls.facility,
            day_of_week=0,
            open_time=time(6, 0),
            close_time=time(22, 0),
        )

    def make_reservation(self, **overrides):
        defaults = dict(
            requester=self.requester,
            requester_type=Reservation.RequesterType.CAMPUS,
            contact_email=self.requester.email,
            event_name="Guest Lecture",
            event_type=Reservation.EventType.ACADEMIC,
            facility=self.facility,
            date=date(2026, 11, 2),
            start_time=time(9, 0),
            end_time=time(11, 0),
            status=Reservation.Status.PENDING,
        )
        defaults.update(overrides)
        reservation = Reservation.objects.create(**defaults)
        reservation.created_by = self.requester
        reservation.save(update_fields=["created_by"])
        return reservation

    def approve_with_commit(self, reservation, actor=None, comment="Test approval"):
        """Approve while capturing the post-commit email dispatch."""
        actor = actor or self.admin
        with self.captureOnCommitCallbacks(execute=True):
            result = workflow.approve_reservation(
                reservation, actor, comment=comment
            )
        return result

    def test_approval_sends_email_to_requester(self):
        reservation = self.make_reservation()
        result = self.approve_with_commit(reservation)

        self.assertEqual(result.status, Reservation.Status.APPROVED)
        self.assertEqual(reservation.approval_email_status, "SENT")
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [self.requester.email])
        self.assertEqual(message.subject, "Your SAS RESERVE reservation has been approved")
        self.assertIn("Guest Lecture", message.body)
        if hasattr(message, "get_body"):
            self.assertIsNotNone(message.get_body(preferencelist=("html",)))
        else:
            self.assertTrue(
                any(ctype == "text/html" for _, ctype in message.alternatives)
            )

    def test_auto_approve_sends_email_too(self):
        reservation = self.make_reservation()
        with self.captureOnCommitCallbacks(execute=True):
            workflow.auto_approve(reservation, self.admin)

        self.assertEqual(reservation.status, Reservation.Status.APPROVED)
        self.assertEqual(reservation.approval_email_status, "SENT")
        self.assertEqual([m.to[0] for m in mail.outbox], [self.requester.email])

    def test_approving_twice_raises_and_sends_only_once(self):
        reservation = self.make_reservation()
        self.approve_with_commit(reservation)
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(ValueError):
                workflow.approve_reservation(reservation, self.admin, comment="Again")
        self.assertEqual(len(mail.outbox), 1)

    def test_no_requester_email_records_no_email_but_keeps_approval(self):
        reservation = self.make_reservation(
            requester=None,
            requester_type=Reservation.RequesterType.EXTERNAL,
            contact_email="",
        )
        result = self.approve_with_commit(reservation)

        self.assertEqual(result.status, Reservation.Status.APPROVED)
        self.assertEqual(reservation.approval_email_status, "NO_EMAIL")
        self.assertEqual(len(mail.outbox), 0)

    def test_external_fallback_never_targets_staff_account(self):
        reservation = self.make_reservation(
            requester=None,
            requester_type=Reservation.RequesterType.EXTERNAL,
            contact_email=self.admin.email,
        )
        result = self.approve_with_commit(reservation)

        # Staff address is rejected as an external fallback recipient.
        self.assertEqual(result.status, Reservation.Status.APPROVED)
        self.assertEqual(reservation.approval_email_status, "NO_EMAIL")
        self.assertEqual(len(mail.outbox), 0)

    def test_smtp_failure_marks_failed_but_keeps_approval(self):
        reservation = self.make_reservation()
        original = workflow.send_reservation_approved

        def fake_send(*args, **kwargs):
            return False, "smtp"

        workflow.send_reservation_approved = fake_send
        try:
            result = self.approve_with_commit(reservation)
        finally:
            workflow.send_reservation_approved = original

        self.assertEqual(result.status, Reservation.Status.APPROVED)
        self.assertEqual(reservation.approval_email_status, "FAILED")

    def test_rejection_sends_no_approval_email(self):
        reservation = self.make_reservation()
        with self.captureOnCommitCallbacks(execute=True):
            workflow.reject_reservation(reservation, self.admin, reason="No room")
        self.assertEqual(reservation.status, Reservation.Status.REJECTED)
        self.assertEqual(reservation.approval_email_status, "NOT_SENT")
        # A rejection notification is expected; an *approval* email is not.
        self.assertNotIn(
            "Your SAS RESERVE reservation has been approved",
            [message.subject for message in mail.outbox],
        )

    def test_editing_approved_reservation_sends_no_second_email(self):
        reservation = self.make_reservation()
        self.approve_with_commit(reservation)
        reservation.event_name = "Guest Lecture (rescheduled)"
        reservation.save(update_fields=["event_name", "updated_at"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(reservation.approval_email_status, "SENT")

    def test_resend_after_failure_recovers(self):
        reservation = self.make_reservation()
        original = workflow.send_reservation_approved

        def fake_send(*args, **kwargs):
            return False, "smtp"

        workflow.send_reservation_approved = fake_send
        try:
            self.approve_with_commit(reservation)
        finally:
            workflow.send_reservation_approved = original
        self.assertEqual(reservation.approval_email_status, "FAILED")

        status_code = workflow.resend_approval_email(reservation, self.admin)
        self.assertEqual(status_code, "SENT")
        self.assertEqual(reservation.approval_email_status, "SENT")
        self.assertEqual(len(mail.outbox), 1)

    def test_resend_skipped_when_already_sent(self):
        reservation = self.make_reservation()
        self.approve_with_commit(reservation)
        status_code = workflow.resend_approval_email(reservation, self.admin)
        self.assertEqual(status_code, "SENT")
        self.assertEqual(len(mail.outbox), 1)

    def test_resend_raises_for_non_approved(self):
        reservation = self.make_reservation()
        with self.assertRaises(ValueError):
            workflow.resend_approval_email(reservation, self.admin)

    def test_approval_email_status_exposed_to_staff_only(self):
        from rest_framework.test import APIRequestFactory

        from reservations.serializers import ReservationDetailSerializer

        reservation = self.make_reservation()
        self.approve_with_commit(reservation)

        factory = APIRequestFactory()
        staff_request = factory.get(f"/api/reservations/{reservation.id}/")
        staff_request.user = self.admin
        staff_data = ReservationDetailSerializer(
            reservation, context={"request": staff_request}
        ).data
        self.assertEqual(staff_data["approval_email_status"], "SENT")

        user_request = factory.get(f"/api/reservations/{reservation.id}/")
        user_request.user = self.requester
        user_data = ReservationDetailSerializer(
            reservation, context={"request": user_request}
        ).data
        self.assertEqual(user_data["approval_email_status"], "")