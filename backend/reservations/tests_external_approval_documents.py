"""Coverage for external-only generated approval letters and secure downloads."""

from datetime import date, time
from decimal import Decimal
from io import BytesIO
import tempfile
from copy import deepcopy
from pathlib import Path
from unittest import mock

from docx import Document
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from equipment.models import Equipment, EquipmentCategory
from facilities.models import Facility, OperatingHour
from reservations.models import ApprovalLetterSettings, Reservation, ReservationFee, ReservationItem
from reservations.services import workflow

User = get_user_model()


def fake_pdf(docx_path, output_dir):
    path = Path(output_dir) / f"{Path(docx_path).stem}.pdf"
    path.write_bytes(b"%PDF-1.4\n" + b"Printable approval letter test content " * 8 + b"\n%%EOF")
    return path


@override_settings(MEDIA_ROOT=f"{tempfile.gettempdir()}/sas-external-approval-test")
class ExternalApprovalDocumentTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("letter-admin", password="pass12345", role=User.Role.ADMIN)
        ApprovalLetterSettings.objects.update_or_create(
            pk=1,
            defaults={
                "authorized_signatory_name": "Francis M. Galon",
                "credentials": "Ph.D.",
                "designation": "Assistant Campus Director for Administration and Finance",
                "sas_staff_display_name": "SAS Administrator",
                "sas_staff_designation": "UED Staff / SAS Staff",
            },
        )
        self.requester = User.objects.create_user(
            "external-requester", password="pass12345", role=User.Role.REQUESTER,
            first_name="Mara", last_name="Santos", email="mara@example.org",
        )
        self.other = User.objects.create_user("other-requester", password="pass12345", role=User.Role.REQUESTER)
        self.facility = Facility.objects.create(
            name="Community Gym", facility_type=Facility.FacilityType.GYMNASIUM, capacity=400,
        )
        for day in range(7):
            OperatingHour.objects.create(facility=self.facility, day_of_week=day, open_time=time(6), close_time=time(22))
        category = EquipmentCategory.objects.create(name="Seating")
        equipment = Equipment.objects.create(name="Plastic chair", category=category, total_quantity=200)
        self.reservation = Reservation.objects.create(
            requester=self.requester,
            requester_type=Reservation.RequesterType.EXTERNAL,
            organization="Bayawan Community Association",
            contact_person="Mara Santos",
            contact_email=self.requester.email,
            contact_phone="09171234567",
            event_name="Community Health Forum",
            description="A public health information session.",
            purpose="Community education",
            expected_participants=120,
            facility=self.facility,
            date=date(2026, 11, 20),
            start_time=time(9),
            end_time=time(12),
            estimated_total=Decimal("7250.00"),
        )
        ReservationItem.objects.create(reservation=self.reservation, equipment=equipment, quantity=120)
        ReservationFee.objects.create(
            reservation=self.reservation, fee_type=ReservationFee.FeeType.EQUIPMENT,
            description="Plastic chairs (120)", quantity=120, unit="piece",
            unit_price=Decimal("10.00"), subtotal=Decimal("1200.00"),
        )
        ReservationFee.objects.create(
            reservation=self.reservation, fee_type=ReservationFee.FeeType.ENVIRONMENTAL,
            description="Environmental fee", quantity=1, unit="flat",
            unit_price=Decimal("250.00"), subtotal=Decimal("250.00"),
        )

    @mock.patch("reservations.services.approval_documents._convert_pdf", side_effect=fake_pdf)
    def test_external_approval_generates_letter_and_attaches_same_pdf(self, _convert):
        with self.captureOnCommitCallbacks(execute=True):
            approved = workflow.approve_reservation(self.reservation, self.admin)
        approved.refresh_from_db()

        self.assertEqual(approved.status, Reservation.Status.APPROVED)
        self.assertEqual(approved.generated_approval_status, Reservation.GeneratedApprovalStatus.GENERATED)
        self.assertEqual(approved.approval_email_status, Reservation.ApprovalEmailStatus.SENT)
        self.assertTrue(approved.generated_approval_pdf.storage.exists(approved.generated_approval_pdf.name))
        self.assertEqual(approved.approval_email_attempts, 1)
        self.assertIsNotNone(approved.approval_email_sent_at)
        self.assertEqual(len(mail.outbox), 1)

        message = mail.outbox[0]
        self.assertEqual(message.to, [self.requester.email])
        self.assertEqual(message.subject, "Reservation Approved — Community Health Forum | SAS RESERVE")
        self.assertIn("Bayawan-Sta. Catalina Campus", message.body)
        self.assertEqual(len(message.attachments), 1)
        filename, attachment, mimetype = message.attachments[0]
        self.assertEqual(filename, f"SAS-RESERVE-APPROVAL-{approved.reservation_id}.pdf")
        self.assertEqual(mimetype, "application/pdf")
        with approved.generated_approval_pdf.open("rb") as saved_pdf:
            self.assertEqual(attachment, saved_pdf.read())

        with approved.generated_approval_docx.open("rb") as saved_docx:
            doc = Document(BytesIO(saved_docx.read()))
        text = "\n".join(p.text for p in doc.paragraphs)
        table_text = "\n".join(cell.text for table in doc.tables for row in table.rows for cell in row.cells)
        all_text = text + "\n" + table_text
        for expected in (
            "Mara Santos", "mara@example.org", "Bayawan Community Association",
            "09171234567", "Community Health Forum", "A public health information session.",
            "Community Gym", "November 20, 2026", "120 units of Plastic chair", "PHP 1,200.00",
            "PHP 250.00", "PHP 7,250.00", "Francis M. Galon", "Ph.D.",
            "Mara Santos", "RESERVATION APPROVAL LETTER",
        ):
            self.assertIn(expected, all_text)
        signatures = doc.tables[-1]
        self.assertEqual(len(signatures.columns), 2)
        self.assertIn("Agreed by the Renter", signatures.cell(0, 0).text)
        self.assertIn("Mara Santos", signatures.cell(3, 0).text)
        self.assertIn("SAS Administrator", signatures.cell(3, 1).text)
        self.assertIn("UED Staff / SAS Staff", signatures.cell(3, 1).text)
        self.assertIn("Francis M. Galon", signatures.cell(4, 0).text)
        self.assertIn("Assistant Campus Director", signatures.cell(4, 0).text)
        self.assertTrue(all("{{" not in value and "}}" not in value for value in all_text.splitlines()))

    def test_approval_trigger_generates_pdf_with_installed_libreoffice(self):
        from reservations.services.approval_documents import (
            LibreOfficeUnavailableError,
            _find_soffice_executable,
        )

        try:
            _find_soffice_executable()
        except LibreOfficeUnavailableError:
            self.skipTest("LibreOffice is not installed in this environment")

        with self.captureOnCommitCallbacks(execute=True):
            approved = workflow.approve_reservation(self.reservation, self.admin)
        approved.refresh_from_db()

        self.assertEqual(approved.status, Reservation.Status.APPROVED)
        self.assertEqual(approved.generated_approval_status, Reservation.GeneratedApprovalStatus.GENERATED)
        with approved.generated_approval_pdf.open("rb") as stream:
            pdf_bytes = stream.read()
        self.assertGreater(len(pdf_bytes), 100)
        self.assertTrue(pdf_bytes.startswith(b"%PDF-"))
        self.assertIn(b"%%EOF", pdf_bytes[-1024:])

        with approved.generated_approval_docx.open("rb") as stream:
            document = Document(BytesIO(stream.read()))
        header = document.sections[0].header
        self.assertGreater(len(header._element.xpath(".//w:drawing")), 0)
        header_text = " ".join(
            [p.text for p in header.paragraphs]
            + [cell.text for table in header.tables for row in table.rows for cell in row.cells]
        )
        self.assertIn("NEGROS ORIENTAL STATE UNIVERSITY", header_text)
        self.assertIn("Bayawan-Sta. Catalina Campus", header_text)
        self.assertIn("SAS RESERVE", header_text)
        self.assertIn("STUDENT AFFAIRS AND SERVICES", header_text)
        self.assertNotIn("VISION", header_text.upper())
        self.assertNotIn("MISSION", header_text.upper())
        header_table = header.tables[0]
        self.assertEqual(len(header_table.rows[0].cells), 1)
        self.assertTrue(all(paragraph.alignment == 1 for paragraph in header_table.cell(0, 0).paragraphs))
        self.assertEqual(document.sections[0].footer.paragraphs[0].text, "")
        self.assertEqual(len(document.tables[-1].columns), 2)
        signatures = document.tables[-1]
        self.assertIn("Mara Santos", signatures.cell(3, 0).text)
        self.assertIn("SAS Administrator", signatures.cell(3, 1).text)
        self.assertIn("UED Staff / SAS Staff", signatures.cell(3, 1).text)
        self.assertIn("Francis M. Galon", signatures.cell(4, 0).text)
        approver_paragraphs = signatures.cell(4, 0).paragraphs
        self.assertGreaterEqual(approver_paragraphs[1].paragraph_format.space_before.pt, 18)
        self.assertGreaterEqual(approver_paragraphs[1].paragraph_format.space_after.pt, 10)
        self.assertEqual(approved.approval_email_status, Reservation.ApprovalEmailStatus.SENT)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].attachments[0][1], pdf_bytes)

    @mock.patch("reservations.services.approval_documents._convert_pdf", side_effect=fake_pdf)
    def test_signatory_updates_apply_to_future_letters_without_rewriting_existing_files(self, convert):
        from reservations.services.approval_documents import generate_approval_documents

        generate_approval_documents(self.reservation)
        old_docx = self.reservation.generated_approval_docx.read()
        old_pdf = self.reservation.generated_approval_pdf.read()

        settings = ApprovalLetterSettings.objects.get(pk=1)
        settings.authorized_signatory_name = "Updated Signatory"
        settings.credentials = "M.P.A."
        settings.designation = "Updated Official Position"
        settings.sas_staff_display_name = "Updated SAS Coordinator"
        settings.sas_staff_designation = "Updated Staff Role"
        settings.letter_title = "Updated Approval Heading"
        settings.approval_message = "Approved for {{event_name}} at {{facility_name}}."
        body = deepcopy(settings.body_content)
        for block in body["content"]:
            if block.get("type") == "heading" and block.get("attrs", {}).get("level") == 1:
                block["content"] = [{"type": "text", "text": settings.letter_title}]
            if block.get("type") == "paragraph" and "This is to inform you" in "".join(
                child.get("text", "") for child in block.get("content", [])
                if child.get("type") == "text"
            ):
                block["content"] = [{"type": "text", "text": settings.approval_message}]
        settings.body_content = body
        settings.save()

        self.reservation.refresh_from_db()
        generate_approval_documents(self.reservation, force=True)
        self.assertEqual(self.reservation.generated_approval_docx.read(), old_docx)
        self.assertEqual(self.reservation.generated_approval_pdf.read(), old_pdf)
        self.assertEqual(convert.call_count, 1)

        future = Reservation.objects.create(
            requester=self.requester,
            requester_type=Reservation.RequesterType.EXTERNAL,
            organization="Bayawan Community Association",
            contact_person="Mara Santos",
            contact_email=self.requester.email,
            event_name="Future Community Forum",
            purpose="Community education",
            facility=self.facility,
            date=date(2026, 12, 1),
            start_time=time(9),
            end_time=time(11),
        )
        generate_approval_documents(future)
        with future.generated_approval_docx.open("rb") as stream:
            doc = Document(BytesIO(stream.read()))
        self.assertIn("Updated Signatory", doc.tables[-1].cell(4, 0).text)
        self.assertIn("M.P.A.", doc.tables[-1].cell(4, 0).text)
        self.assertIn("Updated Official Position", doc.tables[-1].cell(4, 0).text)
        self.assertIn("Updated SAS Coordinator", doc.tables[-1].cell(3, 1).text)
        self.assertIn("Updated Staff Role", doc.tables[-1].cell(3, 1).text)
        body_text = "\n".join(p.text for p in doc.paragraphs)
        self.assertIn("Updated Approval Heading", body_text)
        self.assertIn("Approved for Future Community Forum at Community Gym", body_text)

    @mock.patch("reservations.services.approval_documents._convert_pdf", side_effect=fake_pdf)
    def test_owner_and_staff_can_repeat_download_but_other_requester_cannot(self, _convert):
        self.reservation.status = Reservation.Status.APPROVED
        self.reservation.approved_at = timezone.now()
        self.reservation.approved_by = self.admin
        self.reservation.save()
        from reservations.services.approval_documents import generate_approval_documents
        generate_approval_documents(self.reservation)

        owner = APIClient()
        owner.force_authenticate(self.requester)
        url = f"/api/reservations/{self.reservation.pk}/approval-document/"
        first = owner.get(url)
        second = owner.get(url)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first["Content-Type"], "application/pdf")
        self.assertIn("attachment; filename=", first["Content-Disposition"])
        self.assertEqual(APIClient().get(url).status_code, 401)

        unauthorized = APIClient()
        unauthorized.force_authenticate(self.other)
        self.assertEqual(unauthorized.get(url).status_code, 404)

        staff = APIClient()
        staff.force_authenticate(self.admin)
        preview = staff.get(f"{url}?preview=1")
        self.assertEqual(preview.status_code, 200)
        self.assertTrue(preview["Content-Disposition"].startswith("inline;"))
        self.assertEqual(staff.get(f"/api/reservations/{self.reservation.pk}/approval-document-docx/").status_code, 200)

    def test_internal_approval_keeps_existing_email_without_generated_letter_or_pdf(self):
        self.reservation.requester_type = Reservation.RequesterType.CAMPUS
        self.reservation.requester = self.requester
        self.reservation.save()
        with self.captureOnCommitCallbacks(execute=True):
            approved = workflow.approve_reservation(self.reservation, self.admin)
        approved.refresh_from_db()
        self.assertEqual(approved.status, Reservation.Status.APPROVED)
        self.assertEqual(approved.generated_approval_status, Reservation.GeneratedApprovalStatus.NOT_STARTED)
        self.assertFalse(approved.generated_approval_pdf)
        self.assertEqual(len(mail.outbox), 1)
        self.assertFalse(mail.outbox[0].attachments)

    def test_generation_failure_keeps_approval_and_staff_retry_finishes_pipeline(self):
        with mock.patch(
            "reservations.services.approval_documents._convert_pdf",
            side_effect=RuntimeError("converter unavailable"),
        ):
            with self.captureOnCommitCallbacks(execute=True):
                approved = workflow.approve_reservation(self.reservation, self.admin)
        approved.refresh_from_db()
        self.assertEqual(approved.status, Reservation.Status.APPROVED)
        self.assertEqual(approved.generated_approval_status, Reservation.GeneratedApprovalStatus.FAILED)
        self.assertEqual(approved.approval_email_status, Reservation.ApprovalEmailStatus.NOT_SENT)
        self.assertEqual(len(mail.outbox), 0)

        client = APIClient()
        client.force_authenticate(self.admin)
        with mock.patch("reservations.services.approval_documents._convert_pdf", side_effect=fake_pdf):
            response = client.post(f"/api/reservations/{approved.pk}/retry_approval_document/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        approved.refresh_from_db()
        self.assertEqual(approved.generated_approval_status, Reservation.GeneratedApprovalStatus.GENERATED)
        self.assertEqual(approved.approval_email_status, Reservation.ApprovalEmailStatus.SENT)
        self.assertEqual(len(mail.outbox), 1)

    @mock.patch("reservations.services.approval_documents._convert_pdf", side_effect=fake_pdf)
    def test_explicit_resend_reuses_pdf_and_repeat_approval_does_not_send_again(self, _convert):
        with self.captureOnCommitCallbacks(execute=True):
            approved = workflow.approve_reservation(self.reservation, self.admin)
        approved.refresh_from_db()
        self.assertEqual(len(mail.outbox), 1)
        original_pdf_name = approved.generated_approval_pdf.name

        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.post(f"/api/reservations/{approved.pk}/resend_approval_email/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        approved.refresh_from_db()
        self.assertEqual(approved.generated_approval_pdf.name, original_pdf_name)
        self.assertEqual(approved.approval_email_attempts, 2)
        self.assertEqual(len(mail.outbox), 2)

        duplicate = client.post(f"/api/reservations/{approved.pk}/approve/", {}, format="json")
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(len(mail.outbox), 2)

    @mock.patch("reservations.services.approval_documents._convert_pdf", side_effect=fake_pdf)
    def test_failed_external_delivery_can_be_retried_without_regenerating_pdf(self, _convert):
        with mock.patch("reservations.services.workflow.send_external_reservation_approval", return_value=(False, "smtp_connection")):
            with self.captureOnCommitCallbacks(execute=True):
                approved = workflow.approve_reservation(self.reservation, self.admin)
        approved.refresh_from_db()
        pdf_name = approved.generated_approval_pdf.name
        self.assertEqual(approved.status, Reservation.Status.APPROVED)
        self.assertEqual(approved.generated_approval_status, Reservation.GeneratedApprovalStatus.GENERATED)
        self.assertEqual(approved.approval_email_status, Reservation.ApprovalEmailStatus.FAILED)
        self.assertEqual(approved.approval_email_last_error, "smtp_connection")
        self.assertEqual(len(mail.outbox), 0)

        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.post(f"/api/reservations/{approved.pk}/resend_approval_email/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        approved.refresh_from_db()
        self.assertEqual(approved.generated_approval_pdf.name, pdf_name)
        self.assertEqual(approved.approval_email_status, Reservation.ApprovalEmailStatus.SENT)
        self.assertEqual(approved.approval_email_attempts, 2)
        self.assertEqual(len(mail.outbox), 1)

