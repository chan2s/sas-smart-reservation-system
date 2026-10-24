"""Tests for reservation approval email delivery and its staff-visible status."""

from datetime import date, time

from django.contrib.auth import get_user_model
from django.core import mail
from django.db import transaction
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
            contact_email="incorrect-contact@example.com",
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

    def approve_and_run_callbacks(self, reservation):
        with self.captureOnCommitCallbacks(execute=True):
            result = workflow.approve_reservation(reservation, self.admin)
        result.refresh_from_db()
        return result

    def test_approval_sends_once_to_registered_requester_with_reservation_details(self):
        reservation = self.make_reservation()
        result = self.approve_and_run_callbacks(reservation)

        self.assertEqual(result.status, Reservation.Status.APPROVED)
        self.assertEqual(result.approval_email_status, Reservation.ApprovalEmailStatus.SENT)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [self.requester.email])
        self.assertEqual(message.subject, "Reservation Approved - SAS RESERVE")
        self.assertIn(reservation.reservation_id, message.body)
        self.assertIn("Email Test AVR", message.body)
        self.assertIn("November 2, 2026", message.body)
        self.assertIn("9:00 AM", message.body)
        self.assertIn("11:00 AM", message.body)
        self.assertIn("Approved", message.body)

    def test_administrator_approve_endpoint_delivers_and_exposes_status(self):
        from rest_framework.test import APIClient

        reservation = self.make_reservation()
        client = APIClient()
        client.force_authenticate(self.admin)

        with self.captureOnCommitCallbacks(execute=True):
            response = client.post(
                f"/api/reservations/{reservation.pk}/approve/", {}, format="json"
            )

        reservation.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(reservation.status, Reservation.Status.APPROVED)
        self.assertEqual(
            reservation.approval_email_status, Reservation.ApprovalEmailStatus.SENT
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.requester.email])

    def test_auto_approval_sends_after_commit(self):
        reservation = self.make_reservation()
        with self.captureOnCommitCallbacks(execute=True):
            result = workflow.auto_approve(reservation, self.admin)
        result.refresh_from_db()

        self.assertEqual(result.status, Reservation.Status.APPROVED)
        self.assertEqual(result.approval_email_status, Reservation.ApprovalEmailStatus.SENT)
        self.assertEqual(len(mail.outbox), 1)

    def test_retry_for_previously_approved_reservation_sends_once_and_marks_sent(self):
        """Legacy approvals recorded while automatic emails were disabled."""
        from django.utils import timezone

        reservation = self.make_reservation(
            status=Reservation.Status.APPROVED,
            approved_by=self.admin,
            approved_at=timezone.now(),
            approval_email_status=Reservation.ApprovalEmailStatus.NOT_SENT,
        )

        status = workflow.resend_approval_email(reservation, self.admin)

        self.assertEqual(status, Reservation.ApprovalEmailStatus.SENT)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.requester.email])
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.APPROVED)
        self.assertEqual(
            reservation.approval_email_status, Reservation.ApprovalEmailStatus.SENT
        )

        # A second retry must not send the same approval email twice.
        workflow.resend_approval_email(reservation, self.admin)
        self.assertEqual(len(mail.outbox), 1)

    def test_retry_after_failed_delivery_recovers_and_marks_sent(self):
        from django.utils import timezone

        reservation = self.make_reservation(
            status=Reservation.Status.APPROVED,
            approved_by=self.admin,
            approved_at=timezone.now(),
            approval_email_status=Reservation.ApprovalEmailStatus.FAILED,
        )

        status = workflow.resend_approval_email(reservation, self.admin)

        self.assertEqual(status, Reservation.ApprovalEmailStatus.SENT)
        self.assertEqual(len(mail.outbox), 1)
        reservation.refresh_from_db()
        self.assertEqual(
            reservation.approval_email_status, Reservation.ApprovalEmailStatus.SENT
        )

    def test_retry_failure_keeps_approval_and_records_failed(self):
        from django.utils import timezone

        reservation = self.make_reservation(
            status=Reservation.Status.APPROVED,
            approved_by=self.admin,
            approved_at=timezone.now(),
            approval_email_status=Reservation.ApprovalEmailStatus.NOT_SENT,
        )
        original = workflow.send_reservation_approved

        def fail(*args, **kwargs):
            return False, "smtp_connection"

        workflow.send_reservation_approved = fail
        try:
            status = workflow.resend_approval_email(reservation, self.admin)
        finally:
            workflow.send_reservation_approved = original

        self.assertEqual(status, Reservation.ApprovalEmailStatus.FAILED)
        self.assertEqual(len(mail.outbox), 0)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.APPROVED)
        self.assertEqual(
            reservation.approval_email_status, Reservation.ApprovalEmailStatus.FAILED
        )

    def test_reapproval_after_changes_request_sends_a_fresh_notification(self):
        reservation = self.make_reservation()
        self.approve_and_run_callbacks(reservation)
        self.assertEqual(len(mail.outbox), 1)

        workflow.request_changes(reservation, self.admin, "Please adjust the setup.")
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.PENDING)

        self.approve_and_run_callbacks(reservation)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.APPROVED)
        self.assertEqual(
            reservation.approval_email_status, Reservation.ApprovalEmailStatus.SENT
        )
        self.assertEqual(len(mail.outbox), 2)

    def test_already_approved_reservation_does_not_send_another_approval_email(self):
        reservation = self.make_reservation()
        self.approve_and_run_callbacks(reservation)

        with self.assertRaises(ValueError):
            self.approve_and_run_callbacks(reservation)
        workflow.resend_approval_email(reservation, self.admin)

        self.assertEqual(len(mail.outbox), 1)

    def test_resaving_an_approved_reservation_does_not_send_again(self):
        reservation = self.make_reservation()
        self.approve_and_run_callbacks(reservation)
        self.assertEqual(len(mail.outbox), 1)

        reservation.event_name = "Guest Lecture (renamed)"
        reservation.save()

        self.assertEqual(len(mail.outbox), 1)

    def test_rolled_back_approval_does_not_send_email(self):
        reservation = self.make_reservation()

        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(RuntimeError):
                with transaction.atomic():
                    workflow.approve_reservation(reservation, self.admin)
                    raise RuntimeError("rollback")

        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.PENDING)
        self.assertEqual(reservation.approval_email_status, Reservation.ApprovalEmailStatus.NOT_SENT)
        self.assertEqual(len(mail.outbox), 0)

    def test_smtp_failure_keeps_approval_and_records_failed_state(self):
        reservation = self.make_reservation()
        original = workflow.send_reservation_approved

        def explode(*args, **kwargs):
            raise RuntimeError("SMTP host unreachable")

        workflow.send_reservation_approved = explode
        try:
            with self.captureOnCommitCallbacks(execute=True):
                result = workflow.approve_reservation(reservation, self.admin)
        finally:
            workflow.send_reservation_approved = original

        result.refresh_from_db()
        self.assertEqual(result.status, Reservation.Status.APPROVED)
        self.assertEqual(result.approval_email_status, Reservation.ApprovalEmailStatus.FAILED)
        self.assertEqual(len(mail.outbox), 0)

    def test_email_service_failure_result_is_recorded(self):
        reservation = self.make_reservation()
        original = workflow.send_reservation_approved

        def fail(*args, **kwargs):
            return False, "smtp_authentication"

        workflow.send_reservation_approved = fail
        try:
            with self.captureOnCommitCallbacks(execute=True):
                workflow.approve_reservation(reservation, self.admin)
        finally:
            workflow.send_reservation_approved = original

        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.APPROVED)
        self.assertEqual(reservation.approval_email_status, Reservation.ApprovalEmailStatus.FAILED)

    def test_missing_recipient_is_recorded_without_sending(self):
        reservation = self.make_reservation(
            requester=None,
            requester_type=Reservation.RequesterType.EXTERNAL,
            contact_email="",
        )
        with self.captureOnCommitCallbacks(execute=True):
            workflow.approve_reservation(reservation, self.admin)

        reservation.refresh_from_db()
        self.assertEqual(reservation.approval_email_status, Reservation.ApprovalEmailStatus.NO_EMAIL)
        self.assertEqual(len(mail.outbox), 0)

    def test_external_fallback_never_targets_staff_account(self):
        reservation = self.make_reservation(
            requester=None,
            requester_type=Reservation.RequesterType.EXTERNAL,
            contact_email=self.admin.email,
        )
        with self.captureOnCommitCallbacks(execute=True):
            workflow.approve_reservation(reservation, self.admin)

        reservation.refresh_from_db()
        self.assertEqual(reservation.approval_email_status, Reservation.ApprovalEmailStatus.NO_EMAIL)
        self.assertEqual(len(mail.outbox), 0)

    def test_approval_email_status_exposed_to_staff_only_and_maps_display_label(self):
        from rest_framework.test import APIRequestFactory

        from reservations.serializers import ReservationDetailSerializer

        reservation = self.make_reservation()
        self.approve_and_run_callbacks(reservation)

        factory = APIRequestFactory()
        staff_request = factory.get(f"/api/reservations/{reservation.id}/")
        staff_request.user = self.admin
        staff_data = ReservationDetailSerializer(
            reservation, context={"request": staff_request}
        ).data
        self.assertEqual(staff_data["approval_email_status"], "SENT")
        self.assertEqual(staff_data["approval_email_status_label"], "Sent")

        user_request = factory.get(f"/api/reservations/{reservation.id}/")
        user_request.user = self.requester
        user_data = ReservationDetailSerializer(
            reservation, context={"request": user_request}
        ).data
        self.assertEqual(user_data["approval_email_status"], "")
        self.assertEqual(user_data["approval_email_status_label"], "")
