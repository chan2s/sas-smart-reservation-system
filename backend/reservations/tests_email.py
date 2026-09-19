"""Tests for reservation approval email behavior.

Product decision: automatic approval emails are DISABLED. Approving a
reservation notifies the requester through the in-app notification system
only; no email is sent, and SMTP problems can never affect the approval
itself. Staff can still send an approval email manually via the retry
action (``workflow.resend_approval_email``), whose delivery state is
tracked on the ``Reservation.approval_email_status`` field.
"""

from datetime import date, time

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase

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

    # ------------------------------------------------------------------
    # Approval itself: no email, always succeeds
    # ------------------------------------------------------------------

    def test_approval_sends_no_email(self):
        reservation = self.make_reservation()
        result = workflow.approve_reservation(reservation, self.admin)

        self.assertEqual(result.status, Reservation.Status.APPROVED)
        self.assertEqual(reservation.approval_email_status, "NOT_SENT")
        self.assertEqual(len(mail.outbox), 0)

    def test_auto_approve_sends_no_email(self):
        reservation = self.make_reservation()
        result = workflow.auto_approve(reservation, self.admin)

        self.assertEqual(result.status, Reservation.Status.APPROVED)
        self.assertEqual(reservation.approval_email_status, "NOT_SENT")
        self.assertEqual(len(mail.outbox), 0)

    def test_smtp_failure_never_breaks_approval(self):
        """Even with a completely invalid SMTP configuration, approval works."""
        reservation = self.make_reservation()
        original = workflow.send_reservation_approved

        def explode(*args, **kwargs):
            raise RuntimeError("SMTP host unreachable")

        workflow.send_reservation_approved = explode
        try:
            result = workflow.approve_reservation(reservation, self.admin)
        finally:
            workflow.send_reservation_approved = original

        self.assertEqual(result.status, Reservation.Status.APPROVED)
        self.assertEqual(len(mail.outbox), 0)

    def test_rejection_sends_no_approval_email(self):
        reservation = self.make_reservation()
        workflow.reject_reservation(reservation, self.admin, reason="No room")
        self.assertEqual(reservation.status, Reservation.Status.REJECTED)
        self.assertEqual(reservation.approval_email_status, "NOT_SENT")
        self.assertNotIn(
            "Your SAS RESERVE reservation has been approved",
            [message.subject for message in mail.outbox],
        )

    # ------------------------------------------------------------------
    # Manual staff resend: still works, idempotent, tracked
    # ------------------------------------------------------------------

    def test_manual_resend_sends_email_to_requester(self):
        reservation = self.make_reservation()
        workflow.approve_reservation(reservation, self.admin)
        self.assertEqual(len(mail.outbox), 0)

        status_code = workflow.resend_approval_email(reservation, self.admin)
        self.assertEqual(status_code, "SENT")
        self.assertEqual(reservation.approval_email_status, "SENT")
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [self.requester.email])
        self.assertEqual(message.subject, "Your SAS RESERVE reservation has been approved")
        self.assertIn("Guest Lecture", message.body)

    def test_manual_resend_requires_approved_reservation(self):
        reservation = self.make_reservation()
        with self.assertRaises(ValueError):
            workflow.resend_approval_email(reservation, self.admin)
        self.assertEqual(len(mail.outbox), 0)

    def test_manual_resend_skipped_when_already_sent(self):
        reservation = self.make_reservation()
        workflow.approve_reservation(reservation, self.admin)
        workflow.resend_approval_email(reservation, self.admin)
        status_code = workflow.resend_approval_email(reservation, self.admin)
        self.assertEqual(status_code, "SENT")
        self.assertEqual(len(mail.outbox), 1)

    def test_manual_resend_records_no_email_for_missing_recipient(self):
        reservation = self.make_reservation(
            requester=None,
            requester_type=Reservation.RequesterType.EXTERNAL,
            contact_email="",
        )
        workflow.approve_reservation(reservation, self.admin)
        status_code = workflow.resend_approval_email(reservation, self.admin)
        self.assertEqual(status_code, "NO_EMAIL")
        self.assertEqual(len(mail.outbox), 0)

    def test_external_fallback_never_targets_staff_account(self):
        reservation = self.make_reservation(
            requester=None,
            requester_type=Reservation.RequesterType.EXTERNAL,
            contact_email=self.admin.email,
        )
        workflow.approve_reservation(reservation, self.admin)
        status_code = workflow.resend_approval_email(reservation, self.admin)
        # Staff address is rejected as an external fallback recipient.
        self.assertEqual(status_code, "NO_EMAIL")
        self.assertEqual(len(mail.outbox), 0)

    def test_manual_resend_failure_marks_failed_but_returns(self):
        reservation = self.make_reservation()
        workflow.approve_reservation(reservation, self.admin)
        original = workflow.send_reservation_approved

        def fake_send(*args, **kwargs):
            return False, "smtp"

        workflow.send_reservation_approved = fake_send
        try:
            status_code = workflow.resend_approval_email(reservation, self.admin)
        finally:
            workflow.send_reservation_approved = original

        self.assertEqual(status_code, "FAILED")
        self.assertEqual(reservation.approval_email_status, "FAILED")

    # ------------------------------------------------------------------
    # Serialization: delivery state stays a staff-only diagnostic
    # ------------------------------------------------------------------

    def test_approval_email_status_exposed_to_staff_only(self):
        from rest_framework.test import APIRequestFactory

        from reservations.serializers import ReservationDetailSerializer

        reservation = self.make_reservation()
        workflow.approve_reservation(reservation, self.admin)
        workflow.resend_approval_email(reservation, self.admin)

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
