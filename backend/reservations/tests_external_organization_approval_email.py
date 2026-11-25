"""Automatic approval-letter email for administrator-created external bookings.

Covers requirement 9:

* an administrator creating a reservation for an external organization gets an
  approved reservation, the existing generated approval letter, and an email
  carrying that PDF to the organization's saved address;
* an organization added inline uses the email entered for it;
* a missing organization email, letter-generation failure, or delivery failure
  never deletes the reservation or changes its approved status — the failure is
  recorded and staff can retry from the details page;
* a retry never duplicates an already delivered email;
* internal reservations keep the existing pending workflow.
"""

from datetime import time, timedelta
from io import BytesIO
from pathlib import Path
import tempfile
from unittest import mock

from docx import Document
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Organization
from facilities.models import Facility, OperatingHour
from notifications.email_service import resolve_requester_email
from reservations.models import ApprovalLetterSettings, Reservation, ReservationEvent

User = get_user_model()

RESERVATIONS_URL = "/api/reservations/"


def fake_pdf(docx_path, output_dir):
    path = Path(output_dir) / f"{Path(docx_path).stem}.pdf"
    path.write_bytes(b"%PDF-1.4\n" + b"Printable approval letter test content " * 8 + b"\n%%EOF")
    return path


def _format_date(value):
    return value.strftime("%B %d, %Y").replace(" 0", " ")


def _format_time(value):
    return value.strftime("%I:%M %p").lstrip("0")


@override_settings(MEDIA_ROOT=f"{tempfile.gettempdir()}/gso-external-org-approval-email")
class AdminExternalApprovalEmailTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            "org-admin", password="pass12345", role=User.Role.ADMIN
        )
        self.staff = User.objects.create_user(
            "org-staff", password="pass12345", role=User.Role.STAFF
        )
        ApprovalLetterSettings.objects.update_or_create(
            pk=1,
            defaults={
                "authorized_signatory_name": "Francis M. Galon",
                "credentials": "Ph.D.",
                "designation": "Assistant Campus Director for Administration and Finance",
                "sas_staff_display_name": "GSO Administrator",
                "sas_staff_designation": "UED Staff / GSO Staff",
            },
        )
        self.facility = Facility.objects.create(
            name="Community Gym",
            facility_type=Facility.FacilityType.GYMNASIUM,
            capacity=300,
        )
        for day in range(7):
            OperatingHour.objects.create(
                facility=self.facility,
                day_of_week=day,
                open_time=time(6, 0),
                close_time=time(21, 0),
            )
        self.day = timezone.localdate() + timedelta(days=1)
        self.organization = Organization.objects.create(
            organization_name="Bayawan Community Association",
            organization_type=Organization.OrganizationType.COMMUNITY_ORGANIZATION,
            contact_person="Mara Santos",
            contact_email="office@bayawan-community.example",
            verification_status=Organization.VerificationStatus.PENDING,
        )
        # The separate booking-confirmation email is covered elsewhere; keeping
        # it out of this module leaves the approval email unambiguous.
        confirmation_patcher = mock.patch(
            "reservations.views.confirmations.schedule_booking_confirmation"
        )
        confirmation_patcher.start()
        self.addCleanup(confirmation_patcher.stop)

    def _payload(self, **overrides):
        payload = {
            "facility_id": self.facility.id,
            "date": self.day.isoformat(),
            "start_time": "13:00",
            "end_time": "15:00",
            "event_name": "Community Health Forum",
            "event_type": "SEMINAR",
            "purpose": "Community education",
            "expected_participants": 80,
            "items": [],
            "requester_type": "EXTERNAL",
            "organization": self.organization.organization_name,
            "organization_type": "COMMUNITY",
            "organization_id": self.organization.id,
            "contact_person": "Mara Santos",
        }
        payload.update(overrides)
        return payload

    def _create(self, user, **overrides):
        self.client.force_authenticate(user)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(
                RESERVATIONS_URL, self._payload(**overrides), format="json"
            )

    @mock.patch("reservations.services.approval_documents._convert_pdf", side_effect=fake_pdf)
    def test_admin_created_external_reservation_is_approved_and_emails_pdf(self, _convert):
        response = self._create(self.admin)

        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["status"], "APPROVED")
        self.assertEqual(body["requester_type"], "EXTERNAL")

        # Delivery runs in the post-commit callback, so the persisted row is
        # the authoritative record of generation/email outcome.
        reservation = Reservation.objects.get(pk=body["id"])
        self.assertEqual(reservation.status, Reservation.Status.APPROVED)
        self.assertEqual(reservation.approved_by_id, self.admin.id)
        self.assertIsNotNone(reservation.approved_at)
        self.assertEqual(
            reservation.generated_approval_status,
            Reservation.GeneratedApprovalStatus.GENERATED,
        )
        self.assertIsNotNone(reservation.generated_approval_at)
        self.assertEqual(
            reservation.approval_email_status, Reservation.ApprovalEmailStatus.SENT
        )
        self.assertEqual(reservation.approval_email_attempts, 1)
        self.assertIsNotNone(reservation.approval_email_sent_at)

        # The letter is emailed to the address saved on the organization, with
        # the generated PDF attached.
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [self.organization.contact_email])
        self.assertIn(reservation.reservation_id, message.subject)
        self.assertIn("Community Health Forum", message.subject)
        self.assertIn(f"Reservation ID: {reservation.reservation_id}", message.body)
        self.assertIn("Facility: Community Gym", message.body)
        self.assertIn(f"Event date: {_format_date(reservation.date)}", message.body)
        self.assertIn(
            f"Time: {_format_time(reservation.start_time)} to "
            f"{_format_time(reservation.end_time)}",
            message.body,
        )
        self.assertEqual(len(message.attachments), 1)
        filename, attachment, mimetype = message.attachments[0]
        self.assertEqual(
            filename, f"GSO-RESERVE-APPROVAL-{reservation.reservation_id}.pdf"
        )
        self.assertEqual(mimetype, "application/pdf")
        with reservation.generated_approval_pdf.open("rb") as saved_pdf:
            self.assertEqual(attachment, saved_pdf.read())

        # The attachment is the real approval letter built from the existing
        # template, not a generic notification document.
        with reservation.generated_approval_docx.open("rb") as saved_docx:
            document = Document(BytesIO(saved_docx.read()))
        all_text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        all_text += "\n" + "\n".join(
            cell.text
            for table in document.tables
            for row in table.rows
            for cell in row.cells
        )
        for expected in (
            reservation.reservation_id,
            "Bayawan Community Association",
            "Community Health Forum",
            "Community education",
            "Community Gym",
            _format_date(reservation.date),
            f"{_format_time(reservation.start_time)} to {_format_time(reservation.end_time)}",
            "Francis M. Galon",
        ):
            self.assertIn(expected, all_text)

    @mock.patch("reservations.services.approval_documents._convert_pdf", side_effect=fake_pdf)
    def test_inline_new_organization_uses_the_entered_email(self, _convert):
        response = self._create(
            self.admin,
            organization="Fresh Community Group",
            organization_type="COMMUNITY",
            organization_id=None,
            contact_person="Ana Reyes",
            contact_email="ana@fresh-community.example",
        )

        self.assertEqual(response.status_code, 201, response.content)
        organization = Organization.objects.get(organization_name="Fresh Community Group")
        self.assertEqual(organization.contact_email, "ana@fresh-community.example")
        self.assertEqual(
            organization.verification_status, Organization.VerificationStatus.PENDING
        )
        reservation = Reservation.objects.get(pk=response.json()["id"])
        self.assertEqual(reservation.organization_ref_id, organization.id)
        self.assertEqual(reservation.status, Reservation.Status.APPROVED)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["ana@fresh-community.example"])

    @mock.patch("reservations.services.approval_documents._convert_pdf", side_effect=fake_pdf)
    def test_missing_organization_email_keeps_reservation_and_records_failure(self, _convert):
        self.organization.contact_email = ""
        self.organization.save(update_fields=["contact_email"])

        response = self._create(self.admin)

        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["status"], "APPROVED")

        reservation = Reservation.objects.get(pk=body["id"])
        self.assertEqual(reservation.status, Reservation.Status.APPROVED)
        self.assertEqual(
            reservation.approval_email_status, Reservation.ApprovalEmailStatus.NO_EMAIL
        )
        self.assertEqual(reservation.approval_email_attempts, 1)
        self.assertEqual(reservation.approval_email_last_error, "no_email")
        self.assertEqual(mail.outbox, [])

    @mock.patch(
        "reservations.services.approval_documents._convert_pdf",
        side_effect=RuntimeError("libreoffice failed"),
    )
    def test_generation_failure_does_not_change_approval_and_retry_sends(self, _convert):
        response = self._create(self.admin)

        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["status"], "APPROVED")

        reservation = Reservation.objects.get(pk=body["id"])
        self.assertEqual(reservation.status, Reservation.Status.APPROVED)
        self.assertEqual(reservation.approved_by_id, self.admin.id)
        self.assertEqual(
            reservation.generated_approval_status,
            Reservation.GeneratedApprovalStatus.FAILED,
        )
        self.assertIsNone(reservation.generated_approval_at)
        self.assertEqual(mail.outbox, [])

        with mock.patch(
            "reservations.services.approval_documents._convert_pdf", side_effect=fake_pdf
        ):
            retry = self.client.post(
                f"/api/reservations/{reservation.id}/retry_approval_document/",
                {},
                format="json",
            )

        self.assertEqual(retry.status_code, 200, retry.content)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.APPROVED)
        self.assertEqual(
            reservation.generated_approval_status,
            Reservation.GeneratedApprovalStatus.GENERATED,
        )
        self.assertIsNotNone(reservation.generated_approval_at)
        self.assertEqual(
            reservation.approval_email_status, Reservation.ApprovalEmailStatus.SENT
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.organization.contact_email])

    @mock.patch("reservations.services.approval_documents._convert_pdf", side_effect=fake_pdf)
    def test_delivery_failure_keeps_approval_and_resend_retries(self, _convert):
        with mock.patch(
            "reservations.services.workflow.send_external_reservation_approval",
            return_value=(False, "smtp"),
        ):
            response = self._create(self.admin)

        self.assertEqual(response.status_code, 201, response.content)
        reservation = Reservation.objects.get(pk=response.json()["id"])
        self.assertEqual(reservation.status, Reservation.Status.APPROVED)
        self.assertEqual(
            reservation.approval_email_status, Reservation.ApprovalEmailStatus.FAILED
        )
        self.assertEqual(reservation.approval_email_last_error, "smtp")
        self.assertEqual(reservation.approval_email_attempts, 1)
        self.assertIsNotNone(reservation.generated_approval_pdf)
        self.assertEqual(mail.outbox, [])

        retry = self.client.post(
            f"/api/reservations/{reservation.id}/resend_approval_email/",
            {},
            format="json",
        )

        self.assertEqual(retry.status_code, 200, retry.content)
        self.assertEqual(retry.json()["approval_email_status"], "SENT")
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.APPROVED)
        self.assertEqual(
            reservation.approval_email_status, Reservation.ApprovalEmailStatus.SENT
        )
        self.assertEqual(reservation.approval_email_attempts, 2)
        self.assertEqual(len(mail.outbox), 1)

    @mock.patch("reservations.services.approval_documents._convert_pdf", side_effect=fake_pdf)
    def test_repeated_submission_with_same_key_is_idempotent(self, _convert):
        key = "8a2a6c1e-6f4e-4a14-9f47-1b7a2c9d0e11"

        first = self._create(self.admin, client_request_id=key)
        second = self._create(self.admin, client_request_id=key)

        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(second.status_code, 200, second.content)
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(Reservation.objects.count(), 1)
        reservation = Reservation.objects.get()
        self.assertEqual(reservation.client_request_id, key)
        self.assertEqual(
            reservation.events.filter(
                event_type=ReservationEvent.EventType.APPROVED
            ).count(),
            1,
        )
        # The approval email was sent exactly once for the one reservation.
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.organization.contact_email])

    @mock.patch("reservations.services.approval_documents._convert_pdf", side_effect=fake_pdf)
    def test_retry_after_creation_does_not_send_a_duplicate_email(self, _convert):
        created = self._create(self.admin)
        reservation = Reservation.objects.get(pk=created.json()["id"])
        self.assertEqual(len(mail.outbox), 1)

        retry = self.client.post(
            f"/api/reservations/{reservation.id}/retry_approval_email/",
            {},
            format="json",
        )

        self.assertEqual(retry.status_code, 200, retry.content)
        self.assertEqual(retry.json()["approval_email_status"], "SENT")
        self.assertEqual(len(mail.outbox), 1)
        reservation.refresh_from_db()
        self.assertEqual(reservation.approval_email_attempts, 1)

    def test_internal_administrator_reservation_stays_pending(self):
        internal = Organization.objects.filter(
            organization_type=Organization.OrganizationType.INTERNAL,
            is_active=True,
        ).first()
        self.assertIsNotNone(internal)

        response = self._create(
            self.admin,
            requester_type="CAMPUS",
            organization=internal.organization_name,
            organization_type="",
            organization_id=internal.id,
            contact_person="",
        )

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["status"], "PENDING")
        reservation = Reservation.objects.get(pk=response.json()["id"])
        self.assertEqual(
            reservation.generated_approval_status,
            Reservation.GeneratedApprovalStatus.NOT_STARTED,
        )
        self.assertEqual(mail.outbox, [])

    @mock.patch("reservations.services.approval_documents._convert_pdf", side_effect=fake_pdf)
    def test_staff_created_external_reservation_keeps_manual_approval(self, _convert):
        response = self._create(self.staff)

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["status"], "PENDING")
        self.assertEqual(mail.outbox, [])

    def test_registry_email_is_used_for_administrator_created_reservations(self):
        reservation = Reservation.objects.create(
            requester_type=Reservation.RequesterType.EXTERNAL,
            organization="Bayawan Community Association",
            organization_ref=self.organization,
            contact_person="Mara Santos",
            contact_email="outdated-contact@example.com",
            created_by=self.admin,
            event_name="Community Health Forum",
            facility=self.facility,
            date=self.day,
            start_time=time(13, 0),
            end_time=time(15, 0),
        )

        self.assertEqual(
            resolve_requester_email(reservation), self.organization.contact_email
        )
        self.organization.contact_email = ""
        self.organization.save(update_fields=["contact_email"])
        self.assertEqual(resolve_requester_email(reservation), "")
