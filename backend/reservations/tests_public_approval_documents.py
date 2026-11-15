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

from accounts.models import Organization
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
        # Public internal submissions must select a registered campus
        # organization; this fixture supplies a valid one by default.
        self.campus_organization = Organization.objects.get(organization_code="CAS")

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
            "organization_id": self.campus_organization.id,
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
        if file is None and payload.get("requester_type", "CAMPUS") != "EXTERNAL":
            file = SimpleUploadedFile(
                "authorization.png", png_bytes(), content_type="image/png"
            )
        if file is not None:
            payload["approval_letter_image"] = file
            response = self.client.post(SUBMIT_URL, payload, format="multipart")
        else:
            response = self.client.post(SUBMIT_URL, payload, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        return Reservation.objects.get(pk=response.json()["id"])

    def test_internal_submission_links_the_selected_registered_organization(self):
        organization = Organization.objects.get(organization_code="CAS")

        reservation = self.submit_public(
            payload={
                **self.public_payload(),
                # The client-sent name is never trusted when an id is given.
                "organization": "Typed instead of selected",
                "organization_id": organization.id,
            }
        )

        self.assertEqual(reservation.organization_ref_id, organization.id)
        self.assertEqual(reservation.organization, organization.organization_name)

    def test_internal_submission_rejects_an_inactive_organization(self):
        organization = Organization.objects.get(organization_code="CAS")
        organization.is_active = False
        organization.save(update_fields=["is_active"])

        response = self.client.post(
            SUBMIT_URL,
            {**self.public_payload(), "organization_id": organization.id},
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("organization_id", response.json())

    def test_tracking_by_reference_returns_only_public_fields(self):
        reservation = self.submit_public()

        response = self.client.post(
            TRACK_URL,
            {"reservation_id": reservation.reservation_id},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["reservation_id"], reservation.reservation_id)
        self.assertEqual(response.json()["approval_document_status"], "SUBMITTED")
        for private in ("contact_email", "contact_person", "contact_phone", "notes", "approval_letter_image"):
            self.assertNotIn(private, response.json())

        for payload in ({}, {"reservation_id": ""},
                        {"reservation_id": "SAS-2099-99999"}):
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
            {"reservation_id": reservation.reservation_id},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_account_owner_can_upload_but_another_account_cannot(self):
        requester = User.objects.create_user(
            username="letter-owner", password="pass12345", role=User.Role.REQUESTER
        )
        other = User.objects.create_user(
            username="not-letter-owner", password="pass12345", role=User.Role.REQUESTER
        )
        reservation = Reservation.objects.create(
            requester=requester,
            requester_type=Reservation.RequesterType.CAMPUS,
            contact_email=requester.email,
            event_name="Owner upload test",
            facility=self.facility,
            date=self.day,
            start_time=time(9),
            end_time=time(10),
            status=Reservation.Status.PENDING,
        )
        url = f"/api/reservations/{reservation.pk}/approval-letter-image/"
        payload = {
            "approval_letter_image": SimpleUploadedFile(
                "authorization.png", png_bytes(), content_type="image/png"
            )
        }

        self.client.force_authenticate(other)
        denied = self.client.post(url, payload, format="multipart")
        self.assertEqual(denied.status_code, 404)
        reservation.refresh_from_db()
        self.assertFalse(reservation.approval_letter_image)

        self.client.force_authenticate(requester)
        uploaded = self.client.post(
            url,
            {
                "approval_letter_image": SimpleUploadedFile(
                    "authorization.png", png_bytes(), content_type="image/png"
                )
            },
            format="multipart",
        )
        self.assertEqual(uploaded.status_code, 200, uploaded.content)
        reservation.refresh_from_db()
        self.assertTrue(reservation.approval_letter_image)

    def test_public_upload_rejects_an_account_owned_reservation(self):
        requester = User.objects.create_user(
            username="private-letter-owner", password="pass12345", role=User.Role.REQUESTER
        )
        reservation = Reservation.objects.create(
            requester=requester,
            requester_type=Reservation.RequesterType.CAMPUS,
            contact_email=requester.email,
            event_name="Private reservation",
            facility=self.facility,
            date=self.day,
            start_time=time(9),
            end_time=time(10),
            status=Reservation.Status.PENDING,
        )
        response = self.client.post(
            UPLOAD_URL,
            {
                "reservation_id": reservation.reservation_id,
                "approval_letter_image": SimpleUploadedFile(
                    "authorization.png", png_bytes(), content_type="image/png"
                ),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 404)
        reservation.refresh_from_db()
        self.assertFalse(reservation.approval_letter_image)

    def test_internal_submission_requires_letter_and_document_is_private_to_staff(self):
        missing = self.client.post(SUBMIT_URL, self.public_payload(), format="json")
        self.assertEqual(missing.status_code, 400, missing.content)
        self.assertIn("approval_letter_image", missing.json())

        reservation = self.submit_public()
        self.assertEqual(reservation.approval_document_status, "SUBMITTED")
        self.client.force_authenticate(self.admin)
        self.assertTrue(reservation.approval_letter_image.name.startswith("approval_letters/requester/"))
        self.client.force_authenticate(user=None)

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

    def external_payload(self, **overrides):
        payload = self.public_payload(
            requester_type="EXTERNAL",
            organization="Bayawan Community Association",
            organization_type="COMMUNITY",
        )
        # External submissions are not bound to a registered internal
        # organization, so the internal-only selection is removed.
        payload.pop("organization_id", None)
        payload.update(overrides)
        return payload

    def test_external_submission_without_the_letter_is_accepted(self):
        reservation = self.submit_public(payload=self.external_payload())

        self.assertEqual(reservation.requester_type, Reservation.RequesterType.EXTERNAL)
        self.assertFalse(reservation.approval_letter_required)
        self.assertEqual(reservation.approval_document_status, "NOT_REQUIRED")
        self.assertFalse(reservation.approval_letter_image)

        # SAS can approve it without ever asking for an event approval letter.
        self.client.force_authenticate(self.admin)
        approved = self.client.post(
            f"/api/reservations/{reservation.pk}/approve/", {}, format="json"
        )
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual(approved.json()["status"], "APPROVED")

    def test_external_submission_ignores_an_uploaded_event_approval_letter(self):
        reservation = self.submit_public(
            payload=self.external_payload(),
            file=SimpleUploadedFile(
                "unexpected-letter.png", png_bytes(), content_type="image/png"
            ),
        )

        self.assertFalse(reservation.approval_letter_image)
        self.assertEqual(reservation.approval_document_status, "NOT_REQUIRED")

    def test_external_submission_still_requires_its_other_fields(self):
        response = self.client.post(
            SUBMIT_URL, self.external_payload(contact_person=""), format="json"
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("contact_person", response.json())

    def test_public_upload_is_rejected_for_an_external_reservation(self):
        reservation = Reservation.objects.create(
            requester_type=Reservation.RequesterType.EXTERNAL,
            organization="Bayawan Community Association",
            organization_type=Reservation.OrganizationType.COMMUNITY,
            contact_person="Alex Requester",
            contact_email="alex@example.org",
            event_name="External upload attempt",
            facility=self.facility,
            date=self.day,
            start_time=time(9),
            end_time=time(10),
            status=Reservation.Status.PENDING,
        )
        response = self.client.post(
            UPLOAD_URL,
            {
                "reservation_id": reservation.reservation_id,
                "approval_letter_image": SimpleUploadedFile(
                    "authorization.png", png_bytes(), content_type="image/png"
                ),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 409, response.content)
        reservation.refresh_from_db()
        self.assertFalse(reservation.approval_letter_image)

    def test_external_reservation_stored_with_the_legacy_flag_stays_approvable(self):
        reservation = Reservation.objects.create(
            requester_type=Reservation.RequesterType.EXTERNAL,
            organization="Bayawan Community Association",
            event_name="Legacy external reservation",
            facility=self.facility,
            date=self.day,
            start_time=time(9),
            end_time=time(10),
            status=Reservation.Status.PENDING,
            approval_letter_image=SimpleUploadedFile(
                "previously-uploaded.png", png_bytes(), content_type="image/png"
            ),
        )
        # Simulate a row written before the requirement became internal-only.
        Reservation.objects.filter(pk=reservation.pk).update(
            approval_letter_required=True,
            approval_document_status="AWAITING",
        )
        reservation.refresh_from_db()
        self.assertTrue(reservation.approval_letter_required)
        self.assertTrue(reservation.approval_letter_image.storage.exists(reservation.approval_letter_image.name))

        tracked = self.client.post(
            TRACK_URL, {"reservation_id": reservation.reservation_id}, format="json"
        )
        self.assertEqual(tracked.status_code, 200, tracked.content)
        self.assertEqual(tracked.json()["approval_document_status"], "NOT_REQUIRED")

        self.client.force_authenticate(self.admin)
        response = self.client.post(
            f"/api/reservations/{reservation.pk}/approve/", {}, format="json"
        )

        self.assertEqual(response.status_code, 200, response.content)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.APPROVED)
        self.assertFalse(reservation.approval_letter_required)
        self.assertEqual(reservation.approval_document_status, "SUBMITTED")
        self.assertTrue(reservation.approval_letter_image.storage.exists(reservation.approval_letter_image.name))

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

