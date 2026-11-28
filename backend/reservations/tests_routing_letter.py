"""Tests for equipment-specific routing letters on approved internal reservations."""

from datetime import date, time
from io import BytesIO
from pathlib import Path
import tempfile
from unittest import mock

from docx import Document
from PIL import Image
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Organization
from equipment.models import Equipment, EquipmentCategory
from facilities.models import Facility
from reservations.models import ApprovalLetterSettings, Reservation, ReservationItem
from reservations.services import workflow
from reservations.services.routing_letters import (
    CAS,
    GSO,
    generate_routing_letters,
    routing_letter_eligibility,
)

User = get_user_model()


def fake_pdf_from_docx(docx_path, output_dir):
    """Convert by copying the DOCX text into a small fake PDF.

    Real conversion is LibreOffice's job; keeping the text here lets tests
    prove each document reflects the reservation data without that dependency.
    """
    document = Document(docx_path)
    parts = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            parts.extend(cell.text for cell in row.cells)
    path = Path(output_dir) / f"{Path(docx_path).stem}.pdf"
    path.write_bytes(b"%PDF-1.4\n" + "\n".join(parts).encode("utf-8") + b"\n%%EOF")
    return path


def png_upload(name="event-approval.png"):
    buffer = BytesIO()
    Image.new("RGB", (8, 8), color="navy").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def read_letter(reservation, kind):
    field = (
        reservation.generated_gso_routing_letter_pdf
        if kind == GSO
        else reservation.generated_cas_routing_letter_pdf
    )
    with field.open("rb") as stream:
        return stream.read().decode("utf-8")


def cas_messages(deliver):
    """Messages delivered with the CAS routing letter attachment."""
    messages = []
    for call in deliver.call_args_list:
        message = call.args[0]
        if any(
            name.startswith("GSO-RESERVE-CAS-ROUTING-")
            for name, _content, _mime in message.attachments
        ):
            messages.append(message)
    return messages


@override_settings(MEDIA_ROOT=f"{tempfile.gettempdir()}/gso-routing-letter-test")
class RoutingLetterTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            "routing-admin",
            password="pass12345",
            role=User.Role.ADMIN,
            email="admin@example.edu",
        )
        # The managed internal organizations are seeded by migration, so reuse
        # them instead of creating duplicate acronyms.
        self.cba, _ = Organization.objects.get_or_create(
            acronym="CBA",
            defaults={
                "organization_name": "College of Business Administration",
                "organization_type": Organization.OrganizationType.INTERNAL,
                "verification_status": Organization.VerificationStatus.APPROVED,
            },
        )
        self.cba.organization_type = Organization.OrganizationType.INTERNAL
        self.cba.verification_status = Organization.VerificationStatus.APPROVED
        self.cba.contact_email = "cba-events@example.edu"
        self.cba.save(
            update_fields=[
                "organization_type",
                "verification_status",
                "contact_email",
            ]
        )
        self.cas_org, _ = Organization.objects.get_or_create(
            acronym="CAS",
            defaults={
                "organization_name": "College of Arts and Sciences",
                "organization_type": Organization.OrganizationType.INTERNAL,
                "verification_status": Organization.VerificationStatus.APPROVED,
            },
        )
        self.cas_org.organization_type = Organization.OrganizationType.INTERNAL
        self.cas_org.verification_status = Organization.VerificationStatus.APPROVED
        self.cas_org.contact_email = "cas-office@example.edu"
        self.cas_org.save(
            update_fields=[
                "organization_type",
                "verification_status",
                "contact_email",
            ]
        )
        self.requester = User.objects.create_user(
            "routing-requester",
            password="pass12345",
            role=User.Role.REQUESTER,
            email="requester@example.edu",
            first_name="Juan",
            last_name="Dela Cruz",
            organization=self.cba.organization_name,
            organization_ref=self.cba,
        )
        self.cas_requester = User.objects.create_user(
            "routing-cas-requester",
            password="pass12345",
            role=User.Role.REQUESTER,
            email="cas-requester@example.edu",
            first_name="Maria",
            last_name="Santos",
            organization=self.cas_org.organization_name,
            organization_ref=self.cas_org,
        )
        self.other = User.objects.create_user(
            "routing-other",
            password="pass12345",
            role=User.Role.REQUESTER,
            email="other@example.edu",
        )
        ApprovalLetterSettings.objects.update_or_create(
            pk=1,
            defaults={
                "authorized_signatory_name": "Francis M. Galon",
                "credentials": "Ph.D.",
                "designation": "Assistant Campus Director",
                "sas_staff_display_name": "GSO Staff",
                "sas_staff_designation": "UED Staff / GSO Staff",
            },
        )
        self.facility = Facility.objects.create(
            name="Gymnasium",
            facility_type=Facility.FacilityType.GYMNASIUM,
            capacity=500,
        )
        self.avr = Facility.objects.create(
            name="Audio-Visual Room",
            facility_type=Facility.FacilityType.AVR,
            capacity=100,
        )
        category = EquipmentCategory.objects.create(name="Event Equipment")
        self.sound = Equipment.objects.create(
            name="Sound System", category=category, total_quantity=2
        )
        self.led = Equipment.objects.create(
            name="LED Wall", category=category, total_quantity=1
        )
        self.chairs = Equipment.objects.create(
            name="Plastic Chairs", category=category, total_quantity=100
        )

    def _make(
        self,
        *,
        status=Reservation.Status.PENDING,
        requester_type=Reservation.RequesterType.CAMPUS,
        requester=None,
        equipment=None,
        facility=None,
        with_document=True,
        event_name="Founders Day Program",
    ):
        requester = requester or self.requester
        equipment = (self.sound,) if equipment is None else equipment
        external = requester_type == Reservation.RequesterType.EXTERNAL
        reservation = Reservation.objects.create(
            requester=None if external else requester,
            requester_type=requester_type,
            organization="Community Group" if external else "",
            contact_person="Maria Santos" if external else "",
            contact_email="community@example.org" if external else "",
            event_name=event_name,
            purpose="University anniversary celebration",
            expected_participants=150,
            facility=facility or self.facility,
            date=date(2026, 12, 15),
            start_time=time(9),
            end_time=time(12),
            status=status,
            approval_letter_image=png_upload() if with_document else None,
        )
        for item in equipment:
            ReservationItem.objects.create(
                reservation=reservation, equipment=item, quantity=1
            )
        if status == Reservation.Status.APPROVED:
            reservation.approved_by = self.admin
            reservation.approved_at = timezone.now()
            reservation.save()
        return reservation

    def _approve(self, reservation, deliver=None):
        """Approve through the real workflow and return its delivery mock."""
        if deliver is None:
            deliver = mock.Mock(return_value=(1, None))
        with mock.patch(
            "reservations.services.approval_documents._convert_pdf",
            side_effect=fake_pdf_from_docx,
        ), mock.patch(
            "notifications.email_service._deliver", deliver
        ):
            approved = workflow.approve_reservation(reservation, self.admin)
        approved.refresh_from_db()
        return approved, deliver

    def _generate(self, reservation, *, send_cas_email=False):
        with mock.patch(
            "reservations.services.approval_documents._convert_pdf",
            side_effect=fake_pdf_from_docx,
        ):
            generate_routing_letters(
                reservation, send_cas_email=send_cas_email
            )
        reservation.refresh_from_db()
        return reservation

    # 1 ------------------------------------------------------------------
    def test_approved_internal_gym_sound_system_generates_gso_letter(self):
        reservation = self._make(equipment=(self.sound,))
        approved, _deliver = self._approve(reservation)

        self.assertEqual(approved.status, Reservation.Status.APPROVED)
        self.assertTrue(approved.generated_gso_routing_letter_pdf)
        self.assertTrue(approved.generated_gso_routing_letter_pdf.storage.exists(
            approved.generated_gso_routing_letter_pdf.name
        ))
        self.assertIsNotNone(approved.generated_gso_routing_letter_at)
        self.assertFalse(approved.generated_cas_routing_letter_pdf)
        text = read_letter(approved, GSO)
        for expected in (
            "ROUTING LETTER",
            "Sir Clyde",
            "Sound System",
            "Gymnasium",
            "College of Business Administration",
            "Founders Day Program",
            "December 15, 2026",
            "9:00 AM – 12:00 PM",
            "General Services Office",
            "RESERVATION DETAILS",
            "Respectfully submitted by:",
            "Received by:",
        ):
            self.assertIn(expected, text)
        # The letter is a single request, not a summary or an approval.
        for unwanted in (
            "The equipment will be used only",
            "We respectfully request your approval",
            "Permission granted by",
            "Approved by",
        ):
            self.assertNotIn(unwanted, text)

    # 2 ------------------------------------------------------------------
    def test_approved_internal_gym_led_wall_generates_cas_letter(self):
        reservation = self._make(equipment=(self.led,))
        approved, _deliver = self._approve(reservation)

        self.assertTrue(approved.generated_cas_routing_letter_pdf)
        self.assertIsNotNone(approved.generated_cas_routing_letter_at)
        self.assertFalse(approved.generated_gso_routing_letter_pdf)
        text = read_letter(approved, CAS)
        for expected in (
            "ROUTING LETTER",
            "College of Arts and Sciences",
            "LED Wall",
            "Gymnasium",
            "College of Business Administration",
            "Founders Day Program",
            "To the College of Arts and Sciences:",
            "RESERVATION DETAILS",
            "Requesting department",
            "Respectfully submitted by:",
            "Received by:",
        ):
            self.assertIn(expected, text)
        for unwanted in (
            "The equipment will be used only",
            "We respectfully request your approval",
            "Permission granted by",
            "Approved by",
            "SUBJECT:",
            "Reservation and request details",
            "Expected attendees",
        ):
            self.assertNotIn(unwanted, text)

    # 3 ------------------------------------------------------------------
    def test_both_equipment_types_generate_two_separate_letters(self):
        reservation = self._make(equipment=(self.sound, self.led))
        approved, deliver = self._approve(reservation)

        self.assertTrue(approved.generated_gso_routing_letter_pdf)
        self.assertTrue(approved.generated_cas_routing_letter_pdf)
        self.assertNotEqual(
            approved.generated_gso_routing_letter_pdf.name,
            approved.generated_cas_routing_letter_pdf.name,
        )
        gso_text = read_letter(approved, GSO)
        cas_text = read_letter(approved, CAS)
        self.assertIn("Sound System", gso_text)
        self.assertNotIn("LED Wall", gso_text)
        self.assertIn("LED Wall", cas_text)
        self.assertNotIn("Sound System", cas_text)
        self.assertEqual(len(cas_messages(deliver)), 1)

    # 4 ------------------------------------------------------------------
    def test_cas_requesting_led_wall_does_not_generate_cas_letter(self):
        reservation = self._make(
            requester=self.cas_requester, equipment=(self.sound, self.led)
        )
        approved, _deliver = self._approve(reservation)

        self.assertTrue(approved.generated_gso_routing_letter_pdf)
        self.assertFalse(approved.generated_cas_routing_letter_pdf)
        eligible, reason = routing_letter_eligibility(approved, CAS)
        self.assertFalse(eligible)
        self.assertIn("CAS", reason)

    # 5 ------------------------------------------------------------------
    def test_reservation_without_sound_system_has_no_gso_letter(self):
        reservation = self._make(equipment=(self.led,))
        approved, _deliver = self._approve(reservation)

        self.assertFalse(approved.generated_gso_routing_letter_pdf)
        eligible, reason = routing_letter_eligibility(approved, GSO)
        self.assertFalse(eligible)
        self.assertIn("Sound System", reason)

    # 6 ------------------------------------------------------------------
    def test_reservation_without_led_wall_has_no_cas_letter(self):
        reservation = self._make(equipment=(self.sound,))
        approved, _deliver = self._approve(reservation)

        self.assertFalse(approved.generated_cas_routing_letter_pdf)
        eligible, reason = routing_letter_eligibility(approved, CAS)
        self.assertFalse(eligible)
        self.assertIn("LED Wall", reason)

    # 7 ------------------------------------------------------------------
    def test_external_reservation_never_gets_internal_routing_letters(self):
        reservation = self._make(
            requester_type=Reservation.RequesterType.EXTERNAL,
            equipment=(self.sound, self.led),
            with_document=True,
        )
        self._generate(reservation, send_cas_email=True)
        reservation.refresh_from_db()

        self.assertFalse(reservation.generated_gso_routing_letter_pdf)
        self.assertFalse(reservation.generated_cas_routing_letter_pdf)
        self.assertFalse(routing_letter_eligibility(reservation, GSO)[0])
        self.assertFalse(routing_letter_eligibility(reservation, CAS)[0])

    # 8 ------------------------------------------------------------------
    def test_pending_and_rejected_reservations_get_no_letters(self):
        for status in (Reservation.Status.PENDING, Reservation.Status.REJECTED):
            with self.subTest(status=status):
                reservation = self._make(
                    status=status, equipment=(self.sound, self.led)
                )
                self._generate(reservation, send_cas_email=True)
                reservation.refresh_from_db()
                self.assertFalse(reservation.generated_gso_routing_letter_pdf)
                self.assertFalse(reservation.generated_cas_routing_letter_pdf)

    # 9 ------------------------------------------------------------------
    def test_missing_required_document_prevents_generation(self):
        reservation = self._make(
            status=Reservation.Status.APPROVED,
            equipment=(self.sound, self.led),
            with_document=False,
        )
        self._generate(reservation, send_cas_email=True)
        reservation.refresh_from_db()

        self.assertFalse(reservation.generated_gso_routing_letter_pdf)
        self.assertFalse(reservation.generated_cas_routing_letter_pdf)
        eligible, reason = routing_letter_eligibility(reservation, GSO)
        self.assertFalse(eligible)
        self.assertIn("approval letter", reason)

    # 10 -----------------------------------------------------------------
    def test_completing_requirements_after_approval_generates_on_access(self):
        reservation = self._make(
            status=Reservation.Status.APPROVED,
            equipment=(self.sound, self.led),
            with_document=False,
        )
        self._generate(reservation)
        reservation.refresh_from_db()
        self.assertFalse(reservation.generated_gso_routing_letter_pdf)

        # The required document arrives later through the existing upload path.
        reservation.approval_letter_image = png_upload("late-letter.png")
        reservation.save()

        client = APIClient()
        client.force_authenticate(self.admin)
        with mock.patch(
            "reservations.services.approval_documents._convert_pdf",
            side_effect=fake_pdf_from_docx,
        ):
            response = client.get(
                f"/api/reservations/{reservation.pk}/routing-letter/?kind=gso"
            )
        self.assertEqual(response.status_code, 200)
        reservation.refresh_from_db()
        self.assertTrue(reservation.generated_gso_routing_letter_pdf)
        self.assertTrue(reservation.generated_cas_routing_letter_pdf)

    # 11 -----------------------------------------------------------------
    def test_cas_letter_is_emailed_to_the_requesting_organization(self):
        reservation = self._make(equipment=(self.led,))
        approved, deliver = self._approve(reservation)

        messages = cas_messages(deliver)
        self.assertEqual(len(messages), 1)
        message = messages[0]
        self.assertEqual(message.to, [self.cba.contact_email])
        self.assertIn("CAS Routing Letter", message.subject)
        name, content, mime = message.attachments[0]
        self.assertTrue(name.startswith("GSO-RESERVE-CAS-ROUTING-"))
        self.assertEqual(mime, "application/pdf")
        self.assertTrue(content.startswith(b"%PDF-"))
        self.assertIsNotNone(approved.generated_cas_routing_letter_email_sent_at)

    # 12a ----------------------------------------------------------------
    def test_missing_organization_email_keeps_the_generated_letter(self):
        self.cba.contact_email = ""
        self.cba.save(update_fields=["contact_email"])
        self.requester.email = ""
        self.requester.save(update_fields=["email"])
        reservation = self._make(equipment=(self.led,))
        approved, deliver = self._approve(reservation)

        self.assertTrue(approved.generated_cas_routing_letter_pdf)
        self.assertFalse(cas_messages(deliver))
        self.assertIsNone(approved.generated_cas_routing_letter_email_sent_at)

    # 12b ----------------------------------------------------------------
    def test_cas_email_failure_keeps_the_generated_letter(self):
        reservation = self._make(equipment=(self.led,))
        approved, deliver = self._approve(
            reservation,
            deliver=mock.Mock(return_value=(0, RuntimeError("smtp down"))),
        )

        self.assertTrue(approved.generated_cas_routing_letter_pdf)
        self.assertEqual(len(cas_messages(deliver)), 1)
        self.assertIsNone(approved.generated_cas_routing_letter_email_sent_at)

    # 13 -----------------------------------------------------------------
    def test_repeated_access_does_not_duplicate_letters_or_emails(self):
        reservation = self._make(
            status=Reservation.Status.APPROVED,
            equipment=(self.sound, self.led),
        )
        deliver = mock.Mock(return_value=(1, None))
        with mock.patch(
            "reservations.services.approval_documents._convert_pdf",
            side_effect=fake_pdf_from_docx,
        ) as convert, mock.patch(
            "notifications.email_service._deliver", deliver
        ):
            generate_routing_letters(reservation, send_cas_email=True)
        reservation.refresh_from_db()
        stored = {
            GSO: reservation.generated_gso_routing_letter_pdf.name,
            CAS: reservation.generated_cas_routing_letter_pdf.name,
        }
        conversion_count = convert.call_count
        sent_at = reservation.generated_cas_routing_letter_email_sent_at

        client = APIClient()
        client.force_authenticate(self.admin)
        base = f"/api/reservations/{reservation.pk}/routing-letter/"
        with mock.patch(
            "reservations.services.approval_documents._convert_pdf",
            side_effect=fake_pdf_from_docx,
        ) as again:
            for url in (
                f"{base}?kind=gso",
                f"{base}?kind=cas&preview=1",
                f"{base}?kind=gso",
                f"{base}?kind=cas",
            ):
                response = client.get(url)
                self.assertEqual(
                    response.status_code, 200, f"{url}: {getattr(response, 'data', None)}"
                )

        self.assertEqual(again.call_count, 0)
        reservation.refresh_from_db()
        self.assertEqual(
            reservation.generated_gso_routing_letter_pdf.name, stored[GSO]
        )
        self.assertEqual(
            reservation.generated_cas_routing_letter_pdf.name, stored[CAS]
        )
        self.assertEqual(reservation.status, Reservation.Status.APPROVED)
        self.assertEqual(
            reservation.generated_cas_routing_letter_email_sent_at, sent_at
        )
        self.assertEqual(len(cas_messages(deliver)), 1)
        self.assertEqual(conversion_count, 2)

    # 14 -----------------------------------------------------------------
    def test_routing_letter_access_is_staff_and_owner_scoped(self):
        reservation = self._make(equipment=(self.sound, self.led))
        self._approve(reservation)
        base = f"/api/reservations/{reservation.pk}/routing-letter/"

        for kind in (GSO, CAS):
            self.assertEqual(
                APIClient().get(f"{base}?kind={kind}").status_code, 401
            )

        # Staff keep both letters.
        staff = APIClient()
        staff.force_authenticate(self.admin)
        for kind in (GSO, CAS):
            self.assertEqual(staff.get(f"{base}?kind={kind}").status_code, 200)

        # The reservation's own requester downloads only the CAS letter.
        owner = APIClient()
        owner.force_authenticate(self.requester)
        self.assertEqual(owner.get(f"{base}?kind=cas").status_code, 200)
        self.assertEqual(owner.get(f"{base}?kind=gso").status_code, 404)

        # Another organization's account never reaches this reservation.
        other = APIClient()
        other.force_authenticate(self.other)
        for kind in (GSO, CAS):
            self.assertEqual(other.get(f"{base}?kind={kind}").status_code, 404)

    def test_requester_downloads_the_same_generated_cas_pdf(self):
        reservation = self._make(equipment=(self.sound, self.led))
        approved, deliver = self._approve(reservation)
        self.assertEqual(len(cas_messages(deliver)), 1)
        with approved.generated_cas_routing_letter_pdf.open("rb") as stream:
            stored_bytes = stream.read()

        client = APIClient()
        client.force_authenticate(self.requester)
        url = f"/api/reservations/{approved.pk}/routing-letter/?kind=cas"
        response = client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertEqual(b"".join(response.streaming_content), stored_bytes)

        # Repeated downloads reuse the stored PDF and never resend the email.
        before = approved.generated_cas_routing_letter_at
        again = client.get(url)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(b"".join(again.streaming_content), stored_bytes)
        approved.refresh_from_db()
        self.assertEqual(approved.generated_cas_routing_letter_at, before)
        self.assertEqual(len(cas_messages(deliver)), 1)

    def test_requester_cannot_read_a_cas_letter_that_was_not_generated(self):
        # Approved directly, bypassing the approval hook, so no document exists.
        reservation = self._make(
            status=Reservation.Status.APPROVED,
            equipment=(self.sound, self.led),
        )
        self.assertFalse(reservation.generated_cas_routing_letter_pdf)

        client = APIClient()
        client.force_authenticate(self.requester)
        response = client.get(
            f"/api/reservations/{reservation.pk}/routing-letter/?kind=cas"
        )

        self.assertEqual(response.status_code, 404)
        reservation.refresh_from_db()
        self.assertFalse(reservation.generated_cas_routing_letter_pdf)

    def test_serializer_shows_cas_letter_only_to_its_own_requester(self):
        reservation = self._make(equipment=(self.sound, self.led))
        approved, _deliver = self._approve(reservation)

        owner = APIClient()
        owner.force_authenticate(self.requester)
        data = owner.get(f"/api/reservations/{approved.pk}/").json()
        self.assertFalse(data["gso_routing_letter_available"])
        self.assertTrue(data["cas_routing_letter_available"])
        self.assertIsNotNone(data["cas_routing_letter_generated_at"])

        staff = APIClient()
        staff.force_authenticate(self.admin)
        staff_data = staff.get(f"/api/reservations/{approved.pk}/").json()
        self.assertTrue(staff_data["gso_routing_letter_available"])
        self.assertTrue(staff_data["cas_routing_letter_available"])

        other = APIClient()
        other.force_authenticate(self.other)
        self.assertEqual(
            other.get(f"/api/reservations/{approved.pk}/").status_code, 404
        )

    # 15 -----------------------------------------------------------------
    def test_changes_to_details_and_equipment_update_the_letters(self):
        reservation = self._make(equipment=(self.sound, self.led))
        approved, deliver = self._approve(reservation)
        sent_at = approved.generated_cas_routing_letter_email_sent_at

        approved.event_name = "Renamed Anniversary Program"
        approved.save()
        client = APIClient()
        client.force_authenticate(self.admin)
        base = f"/api/reservations/{approved.pk}/routing-letter/"

        with mock.patch(
            "reservations.services.approval_documents._convert_pdf",
            side_effect=fake_pdf_from_docx,
        ):
            self.assertEqual(client.get(f"{base}?kind=gso").status_code, 200)
        approved.refresh_from_db()
        self.assertIn("Renamed Anniversary Program", read_letter(approved, GSO))
        self.assertNotIn("Founders Day Program", read_letter(approved, GSO))
        self.assertIn("Renamed Anniversary Program", read_letter(approved, CAS))
        self.assertEqual(
            approved.generated_cas_routing_letter_email_sent_at, sent_at
        )
        self.assertEqual(len(cas_messages(deliver)), 1)

        # Removing the LED wall removes its letter instead of leaving it stale.
        approved.items.filter(equipment=self.led).delete()
        with mock.patch(
            "reservations.services.approval_documents._convert_pdf",
            side_effect=fake_pdf_from_docx,
        ):
            self.assertEqual(client.get(f"{base}?kind=gso").status_code, 200)
        approved.refresh_from_db()
        self.assertFalse(approved.generated_cas_routing_letter_pdf)
        self.assertIsNone(approved.generated_cas_routing_letter_at)
        self.assertFalse(approved.generated_cas_routing_letter_email_sent_at)
        self.assertTrue(approved.generated_gso_routing_letter_pdf)
        self.assertEqual(
            client.get(f"{base}?kind=cas").status_code, 404
        )

        # Re-adding the equipment makes the letter available again.
        ReservationItem.objects.create(
            reservation=approved, equipment=self.led, quantity=1
        )
        with mock.patch(
            "reservations.services.approval_documents._convert_pdf",
            side_effect=fake_pdf_from_docx,
        ):
            self.assertEqual(client.get(f"{base}?kind=cas").status_code, 200)
        approved.refresh_from_db()
        self.assertTrue(approved.generated_cas_routing_letter_pdf)

    def test_non_gymnasium_reservation_gets_no_letters(self):
        reservation = self._make(
            status=Reservation.Status.APPROVED,
            facility=self.avr,
            equipment=(self.sound, self.led),
        )
        self._generate(reservation, send_cas_email=True)
        reservation.refresh_from_db()

        self.assertFalse(reservation.generated_gso_routing_letter_pdf)
        self.assertFalse(reservation.generated_cas_routing_letter_pdf)
        eligible, reason = routing_letter_eligibility(reservation, GSO)
        self.assertFalse(eligible)
        self.assertIn("Gymnasium", reason)

    def test_invalid_kind_is_rejected(self):
        reservation = self._make(equipment=(self.sound,))
        self._approve(reservation)
        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.get(
            f"/api/reservations/{reservation.pk}/routing-letter/?kind=other"
        )
        self.assertEqual(response.status_code, 400)
