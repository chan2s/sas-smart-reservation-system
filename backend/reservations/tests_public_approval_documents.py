from datetime import date, time, timedelta
from io import BytesIO
import tempfile
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from facilities.models import Facility, OperatingHour
from reservations.models import Reservation

User = get_user_model()
SUBMIT_URL = "/api/public/reservations/submit/"
TRACK_URL = "/api/public/reservations/track/"
UPLOAD_URL = "/api/public/reservations/approval-letter/"


def png_bytes():
    buffer = BytesIO()
    Image.new("RGB", (8, 8), color="navy").save(buffer, format="PNG")
    return buffer.getvalue()


@override_settings(MEDIA_ROOT=f"{tempfile.gettempdir()}/sas-reservation-test-media")
class PublicApprovalDocumentTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="approval-admin", password="pass12345", role=User.Role.ADMIN
        )
        self.facility = Facility.objects.create(
            name="Public Approval Test Hall",
            facility_type=Facility.FacilityType.AVR,
            capacity=100,
        )
        for weekday in range(7):
            OperatingHour.objects.create(
                facility=self.facility,
                day_of_week=weekday,
                open_time=time(6),
                close_time=time(22),
            )
        self.day = timezone.localdate() + timedelta(days=14)

    def public_payload(self, **overrides):
        payload = {
            "facility_id": self.facility.id,
            "date": self.day.isoformat(),
            "start_time": "09:00",
            "end_time": "11:00",
            "event_name": "Community Assembly",
            "event_type": "SEMINAR",
            "organization": "Community Association",
            "requester_type": "CAMPUS",
            "contact_person": "Alex Requester",
            "contact_email": "alex@example.org",
            "contact_phone": "09171234567",
            "purpose": "Community meeting",
            "expected_participants": 20,
        }
        payload.update(overrides)
        return payload

    @mock.patch("reservations.views.confirmations.schedule_booking_confirmation")
    @mock.patch("reservations.views.notify_staff")
    def submit_public(self, _notify, _confirmation, payload=None, file=None):
        payload = payload or self.public_payload()
        if file is not None:
            payload["approval_letter_image"] = file
            response = self.client.post(SUBMIT_URL, payload, format="multipart")
        else:
            response = self.client.post(SUBMIT_URL, payload, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        return Reservation.objects.get(pk=response.json()["id"])

    def test_tracking_requires_matching_email_and_returns_only_public_fields(self):
        reservation = self.submit_public()

        response = self.client.post(
            TRACK_URL,
            {"reservation_id": reservation.reservation_id, "contact_email": "alex@example.org"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["reservation_id"], reservation.reservation_id)
        self.assertEqual(response.json()["approval_document_status"], "AWAITING")
        for private in ("contact_email", "contact_person", "contact_phone", "notes", "approval_letter_image"):
            self.assertNotIn(private, response.json())

        for email in ("wrong@example.org", ""):
            denied = self.client.post(
                TRACK_URL,
                {"reservation_id": reservation.reservation_id, "contact_email": email},
                format="json",
            )
            self.assertEqual(denied.status_code, 404)
        for payload in ({"reservation_id": "SAS-2099-99999", "contact_email": "alex@example.org"},
                        {"reservation_id": reservation.reservation_id}):
            denied = self.client.post(TRACK_URL, payload, format="json")
            self.assertEqual(denied.status_code, 404)

    def test_tracking_does_not_resolve_account_owned_reservations(self):
        requester = User.objects.create_user(
            username="private-requester",
            password="pass12345",
            role=User.Role.REQUESTER,
            email="private@example.org",
        )
        reservation = Reservation.objects.create(
            requester=requester,
            requester_type=Reservation.RequesterType.CAMPUS,
            contact_email=requester.email,
            event_name="Private account reservation",
            facility=self.facility,
            date=self.day,
            start_time=time(9),
            end_time=time(10),
            status=Reservation.Status.PENDING,
        )
        response = self.client.post(
            TRACK_URL,
            {"reservation_id": reservation.reservation_id, "contact_email": requester.email},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_file_is_optional_then_required_before_approval_and_private_to_staff(self):
        reservation = self.submit_public()
        self.assertEqual(reservation.approval_document_status, "AWAITING")
        self.client.force_authenticate(self.admin)
        denied = self.client.post(f"/api/reservations/{reservation.pk}/approve/", {}, format="json")
        self.assertEqual(denied.status_code, 400)
        self.assertEqual(
            denied.json()["detail"],
            "Cannot approve this reservation because the event approval letter has not been submitted.",
        )
        self.client.force_authenticate(user=None)

        uploaded = self.client.post(
            UPLOAD_URL,
            {
                "reservation_id": reservation.reservation_id,
                "contact_email": "alex@example.org",
                "approval_letter_image": SimpleUploadedFile(
                    "authorization.png", png_bytes(), content_type="image/png"
                ),
            },
            format="multipart",
        )
        self.assertEqual(uploaded.status_code, 200, uploaded.content)
        reservation.refresh_from_db()
        self.assertEqual(reservation.approval_document_status, "SUBMITTED")
        self.assertTrue(reservation.approval_letter_image.name.startswith("approval_letters/requester/"))

        # The private media URL is never served directly.
        raw = self.client.get(f"/media/{reservation.approval_letter_image.name}")
        self.assertEqual(raw.status_code, 404)
        self.assertEqual(
            self.client.get(f"/api/reservations/{reservation.pk}/approval-letter-image/file/").status_code,
            401,
        )

        self.client.force_authenticate(self.admin)
        image = self.client.get(f"/api/reservations/{reservation.pk}/approval-letter-image/file/")
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image["Cache-Control"], "private, no-store")
        approved = self.client.post(f"/api/reservations/{reservation.pk}/approve/", {}, format="json")
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual(approved.json()["status"], "APPROVED")

    def test_initial_image_submission_and_actual_content_validation(self):
        reservation = self.submit_public(
            file=SimpleUploadedFile("signed-letter.png", png_bytes(), content_type="image/png")
        )
        self.assertTrue(reservation.approval_letter_image)
        self.assertEqual(reservation.approval_document_status, "SUBMITTED")

        oversized = self.client.post(
            SUBMIT_URL,
            {
                **self.public_payload(date=(self.day + timedelta(days=14)).isoformat()),
                "approval_letter_image": SimpleUploadedFile(
                    "oversized.png", png_bytes() + (b"0" * (5 * 1024 * 1024)), content_type="image/png"
                ),
            },
            format="multipart",
        )
        self.assertEqual(oversized.status_code, 400)
        self.assertIn("approval_letter_image", oversized.json())

        invalid = self.client.post(
            SUBMIT_URL,
            {
                **self.public_payload(date=(self.day + timedelta(days=7)).isoformat()),
                "approval_letter_image": SimpleUploadedFile(
                    "not-an-image.png", b"this is not png data", content_type="image/png"
                ),
            },
            format="multipart",
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertIn("approval_letter_image", invalid.json())

    def test_legacy_reservations_remain_approvable(self):
        reservation = Reservation.objects.create(
            requester_type=Reservation.RequesterType.CAMPUS,
            organization="Legacy office",
            event_name="Existing legacy reservation",
            facility=self.facility,
            date=self.day,
            start_time=time(9),
            end_time=time(10),
            status=Reservation.Status.PENDING,
        )
        self.assertFalse(reservation.approval_letter_required)
        self.assertEqual(reservation.approval_document_status, "NOT_REQUIRED")
        self.client.force_authenticate(self.admin)
        response = self.client.post(f"/api/reservations/{reservation.pk}/approve/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.content)

