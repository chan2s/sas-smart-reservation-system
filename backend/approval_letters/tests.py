"""Tests for the reservation approval-letter and digital-signature workflow.

Covers: automatic creation after approval (and no duplicates), signing
authorization + duplicate prevention, PDF/DOCX generation, email delivery
(success / failure / retry), document access restrictions, and preservation
of the existing reservation approval workflow.
"""

import tempfile
import re
import xml.etree.ElementTree as ET
from zipfile import ZipFile
from datetime import date, time

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import AuditLog
from approval_letters.documents import build_letter_context
from approval_letters.models import ApprovalLetter
from facilities.models import Facility, OperatingHour
from notifications.email_service import send_approval_letter_signed
from reservations.models import Reservation
from reservations.services import workflow

User = get_user_model()

# Letter documents are stored through the default (filesystem) storage; keep
# the signed PDF/DOCX test artifacts out of the real MEDIA_ROOT.
LETTERS_MEDIA_ROOT = tempfile.mkdtemp(prefix="sas-test-approval-letters-")


@override_settings(MEDIA_ROOT=LETTERS_MEDIA_ROOT)
class ApprovalLetterTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username="letteradmin", password="pass12345", role=User.Role.ADMIN
        )
        cls.signatory = User.objects.create_user(
            username="lettersignatory",
            password="pass12345",
            role=User.Role.ASSISTANT_CAMPUS_DIRECTOR_ADMIN_FINANCE,
            first_name="Position",
            last_name="Holder",
            email="position-holder@school.edu",
        )
        cls.other_staff = User.objects.create_user(
            username="otherstaff", password="pass12345", role=User.Role.STAFF
        )
        cls.requester = User.objects.create_user(
            username="letterrequester",
            password="pass12345",
            role=User.Role.REQUESTER,
            first_name="Juan",
            last_name="Dela Cruz",
            email="juan@campus.edu",
        )
        cls.other_requester = User.objects.create_user(
            username="otherrequester",
            password="pass12345",
            role=User.Role.REQUESTER,
            email="other@campus.edu",
        )
        cls.facility = Facility.objects.create(
            name="Letter Test AVR",
            facility_type=Facility.FacilityType.AVR,
            capacity=50,
            rules=["No food in the AVR", "Return all equipment after use"],
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
            event_name="Guest Lecture",
            event_type=Reservation.EventType.ACADEMIC,
            facility=self.facility,
            date=date(2026, 11, 2),
            start_time=time(9, 0),
            end_time=time(11, 0),
            status=Reservation.Status.PENDING,
            purpose="Educational lecture for students",
        )
        defaults.update(overrides)
        return Reservation.objects.create(**defaults)

    def approve(self, reservation, actor=None):
        """Approve through the EXISTING workflow, running on-commit callbacks."""
        with self.captureOnCommitCallbacks(execute=True):
            result = workflow.approve_reservation(reservation, actor or self.admin)
        result.refresh_from_db()
        return result

    def sign(self, letter, actor=None):
        with self.captureOnCommitCallbacks(execute=True):
            return workflow_sign(letter, actor or self.signatory)

    def sign_via_api(self, letter):
        """POST the sign action, running the post-commit email callback."""
        self.client.force_authenticate(self.signatory)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(f"/api/approval-letters/{letter.pk}/sign/")


def workflow_sign(letter, actor):
    from approval_letters.services import sign_letter

    return sign_letter(letter, actor)


# ---------------------------------------------------------------------------
# Automatic creation
# ---------------------------------------------------------------------------


class LetterCreationTests(ApprovalLetterTestBase):
    def test_letter_created_automatically_after_approval(self):
        reservation = self.approve(self.make_reservation())
        letter = ApprovalLetter.objects.get(reservation=reservation)
        self.assertEqual(letter.status, ApprovalLetter.Status.PENDING_SIGNATURE)
        self.assertEqual(letter.requester, self.requester)
        self.assertEqual(letter.requester_name, "Juan Dela Cruz")
        self.assertEqual(letter.requester_email, "juan@campus.edu")
        self.assertTrue(letter.letter_id.startswith("NORSU-AL-2026-"))
        self.assertFalse(letter.is_signed)
        self.assertIn("-PENDING", letter.docx_file.name)
        self.assertEqual(
            self.signatory.notifications.filter(
                title="Approval letter awaiting signature"
            ).count(),
            1,
        )
        self.assertFalse(
            self.other_staff.notifications.filter(
                title="Approval letter awaiting signature"
            ).exists()
        )

    def test_correspondence_ids_are_unique_across_reservations(self):
        first = self.approve(self.make_reservation())
        second = self.approve(
            self.make_reservation(date=date(2026, 11, 3), event_name="Workshop")
        )
        first_id = ApprovalLetter.objects.get(reservation=first).letter_id
        second_id = ApprovalLetter.objects.get(reservation=second).letter_id
        self.assertNotEqual(first_id, second_id)

    def test_no_duplicate_letter_on_reapproval(self):
        reservation = self.approve(self.make_reservation())
        letter = ApprovalLetter.objects.get(reservation=reservation)

        # Reopen through the existing change-request path, then approve again.
        workflow.request_changes(reservation, self.admin, "Please adjust the time.")
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.PENDING)
        self.approve(reservation)

        letters = ApprovalLetter.objects.filter(reservation=reservation)
        self.assertEqual(letters.count(), 1)
        self.assertEqual(letters.first().pk, letter.pk)

    def test_rejected_reservation_generates_no_letter(self):
        reservation = self.make_reservation()
        workflow.reject_reservation(reservation, self.admin, "Facility unavailable.")
        self.assertFalse(ApprovalLetter.objects.filter(reservation=reservation).exists())

    def test_auto_approve_creates_letter(self):
        reservation = self.make_reservation()
        with self.captureOnCommitCallbacks(execute=True):
            result = workflow.auto_approve(reservation, self.admin)
        result.refresh_from_db()
        self.assertEqual(result.status, Reservation.Status.APPROVED)
        self.assertTrue(ApprovalLetter.objects.filter(reservation=result).exists())

    def test_letter_context_contains_reservation_details(self):
        reservation = self.approve(self.make_reservation())
        letter = ApprovalLetter.objects.get(reservation=reservation)
        context = build_letter_context(letter)
        self.assertEqual(context["reservation_reference"], reservation.reservation_id)
        self.assertEqual(context["requester_name"], "Juan Dela Cruz")
        self.assertEqual(context["facility_name"], "Letter Test AVR")
        self.assertEqual(context["reservation_date"], "November 2, 2026")
        self.assertEqual(context["reservation_start"], "9:00 AM")
        self.assertEqual(context["reservation_end"], "11:00 AM")
        self.assertEqual(context["purpose"], "Educational lecture for students")
        self.assertEqual(
            context["facility_rules"],
            ["No food in the AVR", "Return all equipment after use"],
        )
        self.assertEqual(context["signatory_name"], "")
        self.assertEqual(
            context["signatory_position"],
            "Assistant Campus Director for Administration and Finance",
        )


# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------


class SigningTests(ApprovalLetterTestBase):
    def setUp(self):
        self.client = APIClient()
        self.reservation = self.approve(self.make_reservation())
        self.letter = ApprovalLetter.objects.get(reservation=self.reservation)

    def test_designated_signatory_can_sign_via_api(self):
        response = self.sign_via_api(self.letter)
        self.assertEqual(response.status_code, 200)
        self.letter.refresh_from_db()
        self.assertEqual(self.letter.status, ApprovalLetter.Status.APPROVED)
        self.assertEqual(self.letter.signatory, self.signatory)
        self.assertIsNotNone(self.letter.signed_at)
        self.assertTrue(self.letter.has_signed_pdf)
        self.assertTrue(self.letter.has_signed_docx)

    def test_staff_without_designation_cannot_sign(self):
        self.client.force_authenticate(self.other_staff)
        response = self.client.post(f"/api/approval-letters/{self.letter.pk}/sign/")
        self.assertEqual(response.status_code, 403)
        self.letter.refresh_from_db()
        self.assertEqual(self.letter.status, ApprovalLetter.Status.PENDING_SIGNATURE)

    def test_admin_without_designation_cannot_sign(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(f"/api/approval-letters/{self.letter.pk}/sign/")
        self.assertEqual(response.status_code, 403)

    def test_requester_cannot_sign(self):
        self.client.force_authenticate(self.requester)
        response = self.client.post(f"/api/approval-letters/{self.letter.pk}/sign/")
        self.assertEqual(response.status_code, 403)
        self.letter.refresh_from_db()
        self.assertFalse(self.letter.is_signed)

    def test_unauthenticated_cannot_sign(self):
        response = self.client.post(f"/api/approval-letters/{self.letter.pk}/sign/")
        self.assertIn(response.status_code, (401, 403))

    def test_duplicate_signing_prevented(self):
        self.letter = self.sign(self.letter)
        signed_at = self.letter.signed_at

        self.client.force_authenticate(self.signatory)
        response = self.client.post(f"/api/approval-letters/{self.letter.pk}/sign/")
        self.assertEqual(response.status_code, 400)
        self.letter.refresh_from_db()
        self.assertEqual(self.letter.signed_at, signed_at)
        self.assertEqual(self.letter.signatory, self.signatory)

    def test_signing_refused_when_reservation_cancelled(self):
        workflow.cancel_reservation(self.reservation, self.requester, "Plans changed.")
        with self.assertRaises(Exception):
            self.sign(self.letter)
        self.letter.refresh_from_db()
        self.assertEqual(self.letter.status, ApprovalLetter.Status.PENDING_SIGNATURE)

    def test_signature_records_user_and_timestamp(self):
        letter = self.sign(self.letter)
        self.assertEqual(letter.signatory_id, self.signatory.pk)
        self.assertIsNotNone(letter.signed_at)
        self.assertEqual(letter.signatory_name, "Position Holder")
        self.assertEqual(letter.signatory_username, self.signatory.username)
        self.assertEqual(letter.signatory_email, self.signatory.email)

    def test_signing_does_not_change_reservation_status(self):
        letter = self.sign(self.letter)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, Reservation.Status.APPROVED)
        self.assertEqual(letter.reservation.pk, self.reservation.pk)


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


class DocumentTests(ApprovalLetterTestBase):
    def setUp(self):
        self.reservation = self.approve(self.make_reservation())
        self.letter = ApprovalLetter.objects.get(reservation=self.reservation)

    def test_signed_letter_stores_pdf_and_docx(self):
        letter = self.sign(self.letter)
        self.assertTrue(letter.has_signed_pdf)
        self.assertTrue(letter.has_signed_docx)
        with letter.pdf_file.open("rb") as handle:
            self.assertTrue(handle.read(5).startswith(b"%PDF"))
        with letter.docx_file.open("rb") as handle:
            self.assertEqual(handle.read(2), b"PK")  # DOCX is a ZIP container

    def test_pending_letter_has_no_finalized_documents(self):
        self.assertFalse(self.letter.has_signed_pdf)
        self.assertFalse(self.letter.has_signed_docx)
        # Issuance generates a private draft from the institutional template;
        # it is not exposed as a finalized download before signing.
        self.assertTrue(self.letter.docx_file)

    def test_generated_docx_preserves_template_header_footer_and_populates_body(self):
        from docx import Document

        with self.letter.docx_file.open("rb") as handle:
            document = Document(handle)
        body = "\n".join(
            [paragraph.text for paragraph in document.paragraphs]
            + [cell.text for table in document.tables for row in table.rows for cell in row.cells]
        )
        with self.letter.docx_file.open("rb") as handle:
            with ZipFile(handle) as package:
                header_xml = ET.fromstring(package.read("word/header1.xml"))
                footer_xml = ET.fromstring(package.read("word/footer1.xml"))
                w_ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
                header_text = " ".join(
                    node.text or "" for node in header_xml.iter(f"{w_ns}t")
                ).upper()
                footer_text = " ".join(
                    node.text or "" for node in footer_xml.iter(f"{w_ns}t")
                ).lower()
                package_parts = package.namelist()
        footer = "\n".join(
            cell.text for table in document.sections[0].footer.tables
            for row in table.rows for cell in row.cells
        )
        self.assertIn("RESERVATION APPROVAL LETTER", body)
        self.assertIn(self.letter.letter_id, body + footer)
        self.assertIn(self.reservation.reservation_id, body)
        self.assertIn("MISSION", header_text)
        self.assertIn("QUALITYPOLICY", re.sub(r"\s+", "", header_text))
        self.assertIn("information transmitted by this document", footer_text)
        self.assertTrue(any(name.startswith("word/media/") for name in package_parts))

    def test_pending_letter_cannot_be_downloaded_as_finalized(self):
        client = APIClient()
        client.force_authenticate(self.signatory)
        self.assertEqual(
            client.get(f"/api/approval-letters/{self.letter.pk}/download/pdf/").status_code,
            404,
        )
        self.assertEqual(
            client.get(f"/api/approval-letters/{self.letter.pk}/download/docx/").status_code,
            404,
        )

    def test_raw_media_url_does_not_serve_private_letter_files(self):
        client = APIClient()
        response = client.get(f"/media/{self.letter.docx_file.name}")
        self.assertEqual(response.status_code, 404)

    def test_pending_pdf_preview_is_rendered_unsigned(self):
        # A pending letter's context has no signature timestamp at all.
        pending_letter = ApprovalLetter.objects.get(reservation=self.reservation)
        context = build_letter_context(pending_letter)
        self.assertIsNone(context["signed_at"])
        from approval_letters.documents import render_letter_pdf

        pending_bytes = render_letter_pdf(pending_letter, signed=False)
        self.assertTrue(pending_bytes.startswith(b"%PDF"))
        # And even a SIGNED letter renders a valid, distinct unsigned copy.
        letter = self.sign(pending_letter)
        signed_bytes = render_letter_pdf(letter, signed=True)
        self.assertTrue(signed_bytes.startswith(b"%PDF"))
        self.assertNotEqual(pending_bytes, signed_bytes)


# ---------------------------------------------------------------------------
# Preview + downloads + access control
# ---------------------------------------------------------------------------


class AccessTests(ApprovalLetterTestBase):
    def setUp(self):
        self.client = APIClient()
        self.reservation = self.approve(self.make_reservation())
        self.letter = ApprovalLetter.objects.get(reservation=self.reservation)

    def test_preview_returns_structured_letter_content(self):
        self.client.force_authenticate(self.signatory)
        response = self.client.get(f"/api/approval-letters/{self.letter.pk}/preview/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["letter_id"], self.letter.letter_id)
        self.assertFalse(data["is_signed"])
        self.assertEqual(data["signatory_name"], "")
        self.assertEqual(
            data["signatory_position"],
            "Assistant Campus Director for Administration and Finance",
        )
        self.assertEqual(data["reservation_reference"], self.reservation.reservation_id)
        self.assertIn("No food in the AVR", data["facility_rules"])

    def test_requester_can_download_own_signed_letter(self):
        letter = self.sign(self.letter)
        self.client.force_authenticate(self.requester)
        response = self.client.get(f"/api/approval-letters/{letter.pk}/download/pdf/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment", response["Content-Disposition"])

    def test_requester_can_download_docx_when_available(self):
        letter = self.sign(self.letter)
        self.client.force_authenticate(self.requester)
        response = self.client.get(f"/api/approval-letters/{letter.pk}/download/docx/")
        self.assertEqual(response.status_code, 200)

    def test_other_requester_cannot_download_someone_elses_letter(self):
        letter = self.sign(self.letter)
        self.client.force_authenticate(self.other_requester)
        self.assertEqual(
            self.client.get(f"/api/approval-letters/{letter.pk}/download/pdf/").status_code,
            404,
        )
        self.assertEqual(
            self.client.get(f"/api/approval-letters/{letter.pk}/download/docx/").status_code,
            404,
        )
        # Requesters cannot open the approval workspace.
        self.assertEqual(
            self.client.get(f"/api/approval-letters/{letter.pk}/").status_code, 403
        )

    def test_requester_cannot_open_approval_workspace(self):
        self.client.force_authenticate(self.requester)
        self.assertEqual(self.client.get("/api/approval-letters/").status_code, 403)
        self.assertEqual(
            self.client.get(f"/api/approval-letters/{self.letter.pk}/preview/").status_code,
            403,
        )

    def test_staff_can_download_any_letter(self):
        letter = self.sign(self.letter)
        self.client.force_authenticate(self.admin)
        self.assertEqual(
            self.client.get(f"/api/approval-letters/{letter.pk}/download/pdf/").status_code,
            200,
        )

    def test_pending_letter_not_listed_as_downloadable_for_requester(self):
        self.client.force_authenticate(self.requester)
        response = self.client.get(
            f"/api/reservations/{self.reservation.pk}/"
        )
        self.assertEqual(response.status_code, 200)
        letter_data = response.json().get("approval_letter")
        self.assertIsNotNone(letter_data)
        self.assertEqual(letter_data["status"], "PENDING_SIGNATURE")
        self.assertFalse(letter_data["has_signed_pdf"])


# ---------------------------------------------------------------------------
# Email delivery
# ---------------------------------------------------------------------------


class EmailDeliveryTests(ApprovalLetterTestBase):
    def setUp(self):
        self.client = APIClient()
        self.reservation = self.approve(self.make_reservation())
        self.letter = ApprovalLetter.objects.get(reservation=self.reservation)

    def test_signed_letter_is_emailed_with_attachments(self):
        letter = self.sign(self.letter)
        letter.refresh_from_db()
        self.assertEqual(letter.status, ApprovalLetter.Status.APPROVED)
        self.assertEqual(letter.email_status, ApprovalLetter.EmailStatus.SENT)
        self.assertIsNotNone(letter.emailed_at)
        self.assertIsNotNone(letter.email_attempted_at)

        letter_emails = [
            m for m in mail.outbox if m.subject.startswith("Approved Reservation Letter")
        ]
        self.assertEqual(len(letter_emails), 1)
        message = letter_emails[0]
        self.assertEqual(message.to, [self.requester.email])
        self.assertIn(self.letter.letter_id, message.subject)
        # PDF + DOCX attachments.
        attachments = {name for name, content, mime in message.attachments}
        self.assertEqual(len(attachments), 2)
        self.assertTrue(
            any(name.endswith(".pdf") for name in attachments), attachments
        )
        self.assertTrue(
            any(name.endswith(".docx") for name in attachments), attachments
        )

    def test_email_failure_does_not_undo_signature(self):
        original = send_approval_letter_signed

        def fail(*args, **kwargs):
            return False, "smtp_connection"

        from notifications import email_service

        email_service.send_approval_letter_signed = fail
        try:
            self.letter = self.sign(self.letter)
        finally:
            email_service.send_approval_letter_signed = original

        self.letter.refresh_from_db()
        # Signature intact.
        self.assertIsNotNone(self.letter.signed_at)
        self.assertEqual(self.letter.signatory, self.signatory)
        self.assertTrue(self.letter.has_signed_pdf)
        # Delivery recorded as failed.
        self.assertEqual(self.letter.status, ApprovalLetter.Status.APPROVED)
        self.assertEqual(self.letter.email_status, ApprovalLetter.EmailStatus.FAILED)
        self.assertEqual(self.letter.email_error, "smtp_connection")
        self.assertIsNone(self.letter.emailed_at)
        self.assertIsNotNone(self.letter.email_attempted_at)

    def test_retry_failed_email_succeeds_without_new_signature(self):
        from notifications import email_service

        original = email_service.send_approval_letter_signed
        email_service.send_approval_letter_signed = lambda *a, **k: (False, "smtp")
        try:
            self.letter = self.sign(self.letter)
        finally:
            email_service.send_approval_letter_signed = original
        self.letter.refresh_from_db()
        signed_at = self.letter.signed_at
        pdf_name = self.letter.pdf_file.name

        # The regular approval notification is also in the outbox; clear it so
        # the retry assertions below see exactly the letter email.
        mail.outbox.clear()

        self.client.force_authenticate(self.other_staff)
        response = self.client.post(
            f"/api/approval-letters/{self.letter.pk}/retry-email/"
        )
        self.assertEqual(response.status_code, 200)
        self.letter.refresh_from_db()
        self.assertEqual(self.letter.email_status, ApprovalLetter.EmailStatus.SENT)
        self.assertIsNotNone(self.letter.emailed_at)
        self.assertEqual(self.letter.status, ApprovalLetter.Status.APPROVED)
        # Same letter, same signature, same document — nothing re-created.
        self.assertEqual(self.letter.signed_at, signed_at)
        self.assertEqual(self.letter.pdf_file.name, pdf_name)
        self.assertEqual(ApprovalLetter.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_retry_sent_email_is_refused(self):
        letter = self.sign(self.letter)
        self.client.force_authenticate(self.other_staff)
        response = self.client.post(f"/api/approval-letters/{letter.pk}/retry-email/")
        self.assertEqual(response.status_code, 400)

    def test_requester_cannot_retry_email(self):
        from notifications import email_service

        original = email_service.send_approval_letter_signed
        email_service.send_approval_letter_signed = lambda *a, **k: (False, "smtp")
        try:
            self.letter = self.sign(self.letter)
        finally:
            email_service.send_approval_letter_signed = original

        self.client.force_authenticate(self.requester)
        response = self.client.post(
            f"/api/approval-letters/{self.letter.pk}/retry-email/"
        )
        self.assertEqual(response.status_code, 403)

    def test_no_email_recorded_when_requester_has_no_address(self):
        reservation = self.approve(
            self.make_reservation(requester=None, contact_email="")
        )
        letter = ApprovalLetter.objects.get(reservation=reservation)
        letter = self.sign(letter)
        letter.refresh_from_db()
        self.assertEqual(letter.email_status, ApprovalLetter.EmailStatus.NO_EMAIL)
        # Retryable by design: the requester's email may be added later.
        self.assertTrue(letter.can_retry_email)

    def test_pending_letter_cannot_be_emailed(self):
        from notifications import email_service

        original = email_service.send_approval_letter_signed
        emails_sent = []
        email_service.send_approval_letter_signed = lambda *a, **k: emails_sent.append(a) or (
            True,
            None,
        )
        try:
            with self.captureOnCommitCallbacks(execute=True):
                from approval_letters.services import deliver_signed_letter

                deliver_signed_letter(self.letter.pk)
        finally:
            email_service.send_approval_letter_signed = original
        self.assertEqual(emails_sent, [])
        self.letter.refresh_from_db()
        self.assertEqual(self.letter.status, ApprovalLetter.Status.PENDING_SIGNATURE)


# ---------------------------------------------------------------------------
# Existing workflow preserved
# ---------------------------------------------------------------------------


class WorkflowPreservationTests(ApprovalLetterTestBase):
    def test_regular_approval_email_still_sent_alongside_letter(self):
        reservation = self.make_reservation()
        with self.captureOnCommitCallbacks(execute=True):
            result = workflow.approve_reservation(reservation, self.admin)
        result.refresh_from_db()
        self.assertEqual(result.approval_email_status, "SENT")
        # The original approval notification email (no attachment).
        approval_emails = [
            m for m in mail.outbox if m.subject == "Reservation Approved - SAS RESERVE"
        ]
        self.assertEqual(len(approval_emails), 1)

    def test_reservation_timeline_records_approval_not_signing(self):
        reservation = self.approve(self.make_reservation())
        letter = ApprovalLetter.objects.get(reservation=reservation)
        self.sign(letter)
        reservation.refresh_from_db()
        event_types = [e.event_type for e in reservation.events.all()]
        self.assertIn("APPROVED", event_types)
        self.assertEqual(reservation.status, Reservation.Status.APPROVED)

    def test_letter_list_scoping_for_requester_and_staff(self):
        reservation = self.approve(self.make_reservation())
        letter = ApprovalLetter.objects.get(reservation=reservation)
        # A second reservation for the other requester.
        self.approve(self.make_reservation(requester=self.other_requester))

        client = APIClient()
        client.force_authenticate(self.requester)
        response = client.get("/api/approval-letters/")
        self.assertEqual(response.status_code, 403)

        client.force_authenticate(self.admin)
        response = client.get("/api/approval-letters/")
        self.assertEqual(response.json()["count"], 2)

    def test_signatory_dashboard_lists_pending_and_signed(self):
        reservation = self.approve(self.make_reservation())
        client = APIClient()
        client.force_authenticate(self.signatory)

        pending = client.get("/api/approval-letters/?status=PENDING_SIGNATURE")
        self.assertEqual(pending.json()["count"], 1)

        ApprovalLetter.objects.get(reservation=reservation)
        letter = self.sign(ApprovalLetter.objects.get(reservation=reservation))

        pending = client.get("/api/approval-letters/?status=PENDING_SIGNATURE")
        self.assertEqual(pending.json()["count"], 0)
        signed = client.get("/api/approval-letters/?status=APPROVED")
        self.assertEqual(signed.json()["count"], 1)
        self.assertEqual(signed.json()["results"][0]["letter_id"], letter.letter_id)


# ---------------------------------------------------------------------------
# Module-scoped signatory access + explicit approval action
# ---------------------------------------------------------------------------


class ScopedSignatoryAccessTests(ApprovalLetterTestBase):
    """The designated signatory can use ONLY the Approval Letters module.

    These tests exercise the backend directly (never the SPA): the designation
    removes every SAS-staff capability while preserving the account's ability
    to list, preview, and approve letters. The reservation's own status is
    checked throughout to prove letter approval is a separate transition.
    """

    def setUp(self):
        self.client = APIClient()
        self.reservation = self.approve(self.make_reservation())
        self.letter = ApprovalLetter.objects.get(reservation=self.reservation)

    def _as(self, user) -> APIClient:
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def test_signatory_can_list_and_preview_pending_letter(self):
        client = self._as(self.signatory)

        listing = client.get("/api/approval-letters/?status=PENDING_SIGNATURE")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["count"], 1)

        preview = client.get(f"/api/approval-letters/{self.letter.pk}/preview/")
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()["letter_id"], self.letter.letter_id)

    def test_signatory_is_refused_on_every_other_module(self):
        client = self._as(self.signatory)
        scoped_reads = [
            "/api/reservations/",
            "/api/facilities/",
            "/api/equipment/",
            "/api/facility-resources/",
            "/api/maintenance/",
            "/api/analytics/summary/",
            "/api/calendar/events/?start=2026-11-02&end=2026-11-02",
        ]
        for path in scoped_reads:
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 403, response.content)
                self.assertEqual(response.json()["code"], "approval_letters_only")

        # Administrator-only / staff-only surfaces are refused by their own
        # permission classes as well (the signatory is not SAS staff).
        for path in (
            "/api/auth/users/",
            "/api/auth/audit-log/",
            "/api/auth/login-activity/",
            "/api/analytics/trends/",
            "/api/reports/",
        ):
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 403, response.content)

        # It also cannot approve, edit, cancel, or check in the reservation.
        for action in ("approve", "reject", "request_changes", "cancel"):
            with self.subTest(action=action):
                response = client.post(
                    f"/api/reservations/{self.reservation.pk}/{action}/",
                    {},
                    format="json",
                )
                self.assertEqual(response.status_code, 403, response.content)

    def test_signatory_can_approve_letter_through_approve_action(self):
        client = self._as(self.signatory)
        with self.captureOnCommitCallbacks(execute=True):
            response = client.post(
                f"/api/approval-letters/{self.letter.pk}/approve/", format="json"
            )
        self.assertEqual(response.status_code, 200, response.content)

        self.letter.refresh_from_db()
        self.assertEqual(self.letter.status, ApprovalLetter.Status.APPROVED)
        self.assertEqual(self.letter.signatory, self.signatory)
        self.assertIsNotNone(self.letter.signed_at)
        self.assertTrue(self.letter.has_signed_pdf)

        # The approval is attributed in the audit trail.
        audit = AuditLog.objects.filter(
            action=AuditLog.Action.APPROVAL_LETTER_APPROVED,
            object_id=self.letter.letter_id,
        ).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.actor, self.signatory)
        self.assertIn(f"user id {self.signatory.pk}", audit.detail)

        # Letter approval NEVER changes the reservation's status.
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, Reservation.Status.APPROVED)
        self.assertEqual(ApprovalLetter.objects.count(), 1)

    def test_repeated_approval_is_refused_without_duplicates(self):
        client = self._as(self.signatory)
        with self.captureOnCommitCallbacks(execute=True):
            first = client.post(
                f"/api/approval-letters/{self.letter.pk}/approve/", format="json"
            )
        self.assertEqual(first.status_code, 200, first.content)
        self.letter.refresh_from_db()
        approved_at = self.letter.signed_at

        second = client.post(
            f"/api/approval-letters/{self.letter.pk}/approve/", format="json"
        )
        self.assertEqual(second.status_code, 400)
        self.letter.refresh_from_db()
        self.assertEqual(self.letter.signed_at, approved_at)
        self.assertEqual(
            AuditLog.objects.filter(
                action=AuditLog.Action.APPROVAL_LETTER_APPROVED,
                object_id=self.letter.letter_id,
            ).count(),
            1,
        )
        self.assertEqual(ApprovalLetter.objects.count(), 1)

    def test_unauthorized_accounts_cannot_approve_through_api(self):
        for account in (self.other_staff, self.admin, self.requester):
            with self.subTest(account=account.username):
                client = self._as(account)
                response = client.post(
                    f"/api/approval-letters/{self.letter.pk}/approve/",
                    format="json",
                )
                self.assertEqual(response.status_code, 403, response.content)

        for account in (self.other_staff, self.requester):
            with self.subTest(workspace_account=account.username):
                response = self._as(account).get("/api/approval-letters/")
                self.assertEqual(response.status_code, 403, response.content)
                response = self._as(account).get(
                    f"/api/approval-letters/{self.letter.pk}/preview/"
                )
                self.assertEqual(response.status_code, 403, response.content)

        self.letter.refresh_from_db()
        self.assertEqual(self.letter.status, ApprovalLetter.Status.PENDING_SIGNATURE)
        self.assertIsNone(self.letter.signatory_id)
        self.assertIsNone(self.letter.signed_at)

    def test_ordinary_staff_cannot_assign_themselves_the_position_role(self):
        response = self._as(self.other_staff).patch(
            f"/api/auth/users/{self.other_staff.pk}/",
            {"role": User.Role.ASSISTANT_CAMPUS_DIRECTOR_ADMIN_FINANCE},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.other_staff.is_authorized_letter_approver)
        response = self._as(self.other_staff).post(
            f"/api/approval-letters/{self.letter.pk}/approve/",
            format="json",
        )
        self.assertEqual(response.status_code, 403, response.content)
        self.letter.refresh_from_db()
        self.assertEqual(self.letter.status, ApprovalLetter.Status.PENDING_SIGNATURE)

    def test_role_removal_revokes_workspace_access(self):
        response = self._as(self.admin).patch(
            f"/api/auth/users/{self.signatory.pk}/",
            {"role": User.Role.REQUESTER},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.signatory.refresh_from_db()
        denied = self._as(self.signatory).get("/api/approval-letters/")
        self.assertEqual(denied.status_code, 403)

    def test_account_deactivation_revokes_workspace_access(self):
        response = self._as(self.admin).post(
            f"/api/auth/users/{self.signatory.pk}/status/",
            {"is_active": False},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.signatory.refresh_from_db()
        denied = self._as(self.signatory).get("/api/approval-letters/")
        self.assertEqual(denied.status_code, 403)

    def test_role_transfer_preserves_historical_approver_and_reservation(self):
        client = self._as(self.signatory)
        with self.captureOnCommitCallbacks(execute=True):
            approved = client.post(
                f"/api/approval-letters/{self.letter.pk}/approve/", format="json"
            )
        self.assertEqual(approved.status_code, 200, approved.content)
        self.letter.refresh_from_db()
        original_attribution = (
            self.letter.signatory_id,
            self.letter.signatory_name,
            self.letter.signatory_username,
            self.letter.signatory_email,
            self.letter.signed_at,
        )

        admin = self._as(self.admin)
        removed = admin.patch(
            f"/api/auth/users/{self.signatory.pk}/",
            {"role": User.Role.REQUESTER},
            format="json",
        )
        self.assertEqual(removed.status_code, 200, removed.content)
        successor = User.objects.create_user(
            username="lettersuccessor",
            password="pass12345",
            email="successor@school.edu",
        )
        assigned = admin.patch(
            f"/api/auth/users/{successor.pk}/",
            {"role": User.Role.ASSISTANT_CAMPUS_DIRECTOR_ADMIN_FINANCE},
            format="json",
        )
        self.assertEqual(assigned.status_code, 200, assigned.content)
        self.letter.refresh_from_db()
        self.assertEqual(
            (
                self.letter.signatory_id,
                self.letter.signatory_name,
                self.letter.signatory_username,
                self.letter.signatory_email,
                self.letter.signed_at,
            ),
            original_attribution,
        )
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, Reservation.Status.APPROVED)

    def test_approver_cannot_use_retry_email_action(self):
        client = self._as(self.signatory)
        response = client.post(
            f"/api/approval-letters/{self.letter.pk}/retry-email/",
            format="json",
        )
        self.assertEqual(response.status_code, 403, response.content)

