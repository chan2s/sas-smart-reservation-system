from datetime import date, time
from io import BytesIO
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from rest_framework.test import APIClient
from docx import Document

from facilities.models import Facility
from reservations.models import (
    ApprovalLetterSettings,
    ApprovalLetterTemplateVersion,
    Reservation,
    default_approval_letter_body,
)

User = get_user_model()
URL = "/api/admin/settings/approval-letter/"


class ApprovalLetterSettingsApiTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            "approval-settings-admin", password="pass12345", role=User.Role.ADMIN
        )
        self.requester = User.objects.create_user(
            "approval-settings-requester", password="pass12345", role=User.Role.REQUESTER
        )
        self.client = APIClient()

    def test_admin_can_read_update_and_reload_signatory_configuration(self):
        self.client.force_authenticate(self.admin)
        initial = self.client.get(URL)
        self.assertEqual(initial.status_code, 200)
        self.assertEqual(initial.data["approval_label"], "Approved by:")

        response = self.client.patch(URL, {
            "authorized_signatory_name": "A. Administrator",
            "credentials": "M.P.A.",
            "designation": "Campus Administration Director",
            "approval_label": "Approved by:",
            "sas_staff_display_name": "Campus Services Admin",
            "sas_staff_designation": "Facilities Approval Staff",
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            ApprovalLetterSettings.objects.get(pk=1).authorized_signatory_name,
            "A. Administrator",
        )
        self.assertEqual(self.client.get(URL).data["designation"], "Campus Administration Director")
        self.assertEqual(self.client.get(URL).data["sas_staff_display_name"], "Campus Services Admin")
        self.assertEqual(self.client.get(URL).data["sas_staff_designation"], "Facilities Approval Staff")
        persisted = ApprovalLetterSettings.objects.get(pk=1)
        persisted.refresh_from_db()
        self.assertEqual(persisted.sas_staff_display_name, "Campus Services Admin")

    def test_non_admin_cannot_read_or_update_signatory_configuration(self):
        original_name = ApprovalLetterSettings.objects.get(pk=1).authorized_signatory_name
        self.client.force_authenticate(self.requester)
        self.assertEqual(self.client.get(URL).status_code, 403)
        self.assertEqual(self.client.patch(URL, {
            "authorized_signatory_name": "Unauthorized Update",
            "designation": "Unauthorized",
            "sas_staff_display_name": "Unauthorized Staff",
            "sas_staff_designation": "Unauthorized Designation",
        }, format="json").status_code, 403)
        self.assertEqual(
            ApprovalLetterSettings.objects.get(pk=1).authorized_signatory_name,
            original_name,
        )

    def test_required_signatory_fields_are_validated_server_side(self):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(URL, {
            "authorized_signatory_name": "",
            "designation": "",
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("authorized_signatory_name", response.data)
        self.assertIn("designation", response.data)


class ApprovalLetterManagementWorkflowTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            "letter-management-admin", password="pass12345", role=User.Role.ADMIN
        )
        self.requester = User.objects.create_user(
            "letter-management-requester", password="pass12345",
            role=User.Role.REQUESTER, first_name="Taylor", last_name="Requester",
            email="taylor@example.org",
        )
        self.facility = Facility.objects.create(
            name="Preview Hall", facility_type=Facility.FacilityType.GYMNASIUM,
            capacity=200,
        )
        self.reservation = Reservation.objects.create(
            requester=self.requester,
            requester_type=Reservation.RequesterType.EXTERNAL,
            organization="Sample Community Group",
            contact_person="Taylor Requester",
            contact_email=self.requester.email,
            event_name="Sample Forum",
            purpose="Community education",
            expected_participants=40,
            facility=self.facility,
            date=date(2026, 12, 15),
            start_time=time(9),
            end_time=time(11),
            status=Reservation.Status.APPROVED,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.settings_row, _ = ApprovalLetterSettings.objects.update_or_create(
            pk=1,
            defaults={
                "authorized_signatory_name": "Campus Signatory",
                "credentials": "M.P.A.",
                "designation": "Campus Director",
                "approval_label": "Approved by:",
                "sas_staff_display_name": "SAS Administrator",
                "sas_staff_designation": "UED Staff / SAS Staff",
            },
        )
        ApprovalLetterTemplateVersion.objects.all().delete()
        ApprovalLetterTemplateVersion.objects.create(
            version=1,
            configuration={
                field: getattr(self.settings_row, field)
                for field in (
                    "authorized_signatory_name", "credentials", "designation", "approval_label",
                    "sas_staff_display_name", "sas_staff_designation",
                    "letter_title", "approval_message", "introductory_paragraphs",
                    "instructions_template", "additional_content", "footer_disclaimer",
                    "body_content",
                )
            },
            modified_by=self.admin,
            change_note="Test baseline",
        )

    def test_admin_saves_versioned_wording_and_can_restore_a_previous_version(self):
        response = self.client.patch(URL, {
            "letter_title": "Community Reservation Approval",
            "approval_message": "Approved for {{event_name}} at {{facility_name}}.",
            "change_note": "Updated community approval wording",
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["version"], 2)
        history = self.client.get(URL + "versions/")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.data["results"][0]["modified_by_name"], self.admin.display_name)
        self.assertEqual(history.data["results"][0]["configuration"]["letter_title"], "Community Reservation Approval")

        restored = self.client.post(URL + "versions/1/restore/", {}, format="json")
        self.assertEqual(restored.status_code, 200, restored.data)
        self.assertEqual(restored.data["letter_title"], "RESERVATION APPROVAL LETTER")
        self.assertEqual(restored.data["version"], 3)
        self.assertEqual(
            ApprovalLetterTemplateVersion.objects.get(version=3).change_note,
            "Restored version 1",
        )

    def test_unsupported_placeholders_are_rejected_before_saving(self):
        response = self.client.patch(URL, {
            "approval_message": "Unsafe {{python_expression}}",
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("approval_message", response.data)
        self.settings_row.refresh_from_db()
        self.assertNotIn("python_expression", self.settings_row.approval_message)

    def test_rich_letter_body_rejects_unsupported_nodes_and_placeholders(self):
        body = default_approval_letter_body()
        body["content"].insert(2, {
            "type": "paragraph",
            "attrs": {"spaceAfter": 4},
            "content": [{"type": "text", "text": "{{account_password}}"}],
        })
        response = self.client.patch(URL, {"body_content": body}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("body_content", response.data)

        unsafe = default_approval_letter_body()
        unsafe["content"].insert(2, {"type": "rawHtml", "content": []})
        response = self.client.patch(URL, {"body_content": unsafe}, format="json")
        self.assertEqual(response.status_code, 400)

        reordered = default_approval_letter_body()
        slots = [node for node in reordered["content"] if node["type"] in {
            "documentMetadata", "reservationDetails", "reservationConditions",
        }]
        reordered["content"] = [
            node for node in reordered["content"] if node["type"] not in {
                "documentMetadata", "reservationDetails", "reservationConditions",
            }
        ] + list(reversed(slots))
        response = self.client.patch(URL, {"body_content": reordered}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_template_history_is_paged_three_newest_first(self):
        for version in range(2, 6):
            response = self.client.patch(URL, {
                "approval_message": f"Approval version {version}.",
            }, format="json")
            self.assertEqual(response.status_code, 200, response.data)

        first_page = self.client.get(URL + "versions/?page=1")
        second_page = self.client.get(URL + "versions/?page=2")
        self.assertEqual(first_page.data["page_size"], 3)
        self.assertEqual(first_page.data["count"], 5)
        self.assertEqual(first_page.data["pages"], 2)
        self.assertEqual([row["version"] for row in first_page.data["results"]], [5, 4, 3])
        self.assertEqual([row["version"] for row in second_page.data["results"]], [2, 1])

        restored = self.client.post(URL + "versions/1/restore/", {}, format="json")
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.data["version"], 6)
        self.assertEqual(ApprovalLetterTemplateVersion.objects.count(), 6)

    @mock.patch("reservations.services.approval_documents._convert_pdf")
    def test_draft_preview_resolves_placeholders_without_workflow_side_effects(self, convert):
        body = default_approval_letter_body()
        body["content"].insert(6, {
            "type": "paragraph",
            "attrs": {"spaceAfter": 4},
            "content": [{"type": "text", "text": "Editable draft for {{event_name}}."}],
        })

        def fake_convert(docx_path, output_dir):
            doc = Document(BytesIO(Path(docx_path).read_bytes()))
            paragraphs = "\n".join(p.text for p in doc.paragraphs)
            cells = "\n".join(
                cell.text for table in doc.tables for row in table.rows for cell in row.cells
            )
            generated_text = paragraphs + "\n" + cells
            self.assertIn("Taylor Requester", generated_text)
            self.assertIn("Sample Forum", generated_text)
            self.assertIn("Preview Hall", generated_text)
            self.assertIn("Campus Signatory", generated_text)
            self.assertIn("Editable draft for Sample Forum.", generated_text)
            self.assertNotIn("{{", generated_text)
            pdf_path = Path(output_dir) / "preview.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\npreview test bytes\n%%EOF")
            return pdf_path

        convert.side_effect = fake_convert
        response = self.client.post("/api/admin/settings/approval-letter/preview/", {
            "letter_title": "Draft Preview",
            "approval_message": "Request {{reservation_reference}} for {{event_name}} is approved.",
            "body_content": body,
            "reservation_reference": self.reservation.reservation_id,
        }, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(response["X-Approval-Preview-Reservation"], self.reservation.reservation_id)
        self.assertEqual(response.content, b"%PDF-1.4\npreview test bytes\n%%EOF")
        self.assertEqual(self.reservation.status, Reservation.Status.APPROVED)
        self.assertEqual(self.reservation.generated_approval_status, Reservation.GeneratedApprovalStatus.NOT_STARTED)
        self.assertFalse(self.reservation.generated_approval_pdf)
        self.assertEqual(mail.outbox, [])
        self.settings_row.refresh_from_db()
        self.assertNotIn("Taylor Requester", str(self.settings_row.body_content))

    def test_non_admin_cannot_preview_or_restore_template_versions(self):
        self.client.force_authenticate(self.requester)
        self.assertEqual(self.client.post(
            "/api/admin/settings/approval-letter/preview/", {}, format="json"
        ).status_code, 403)
        self.assertEqual(self.client.post(
            URL + "versions/1/restore/", {}, format="json"
        ).status_code, 403)
