"""Public and administrator external-organization entry.

Covers the account-free organization workflow on the reservation forms:

* a typed external organization name is resolved against the registry
  (normalized), reusing an existing record when one matches;
* a name that does not exist is saved automatically before the reservation;
* capitalization / spacing variants never create a second record;
* a public search endpoint offers existing identity-only records;
* administrators can select the PENDING records created by public requests and
  add a new organization directly from the reservation form;
* internal-organization reservations are untouched.
"""

from datetime import time, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Organization
from facilities.models import Facility, OperatingHour

from .models import Reservation

User = get_user_model()

PUBLIC_SUBMIT_URL = "/api/public/reservations/submit/"
PUBLIC_ORGANIZATION_URL = "/api/public/reservations/organizations/"
RESERVATIONS_URL = "/api/reservations/"
ORGANIZATIONS_URL = "/api/auth/organizations/"


def _external_organizations():
    return Organization.objects.exclude(
        organization_type=Organization.OrganizationType.INTERNAL
    )


class ExternalOrganizationEntryTestBase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.facility = Facility.objects.create(
            name="Gymnasium",
            facility_type=Facility.FacilityType.GYMNASIUM,
            capacity=300,
        )
        OperatingHour.objects.create(
            facility=self.facility,
            day_of_week=0,
            open_time=time(6, 0),
            close_time=time(21, 0),
        )
        # Operating hours above apply to Monday; pick the next Monday.
        self.day = timezone.localdate() + timedelta(days=1)
        while self.day.weekday() != 0:
            self.day += timedelta(days=1)

    def _public_payload(self, name, *, organization_type="SCHOOL", **overrides):
        payload = {
            "facility_id": self.facility.id,
            "date": self.day.isoformat(),
            "start_time": "09:00",
            "end_time": "11:00",
            "event_name": "Community Seminar",
            "event_type": "SEMINAR",
            "purpose": "Community Seminar",
            "expected_participants": 80,
            "items": [],
            "requester_type": "EXTERNAL",
            "organization": name,
            "organization_type": organization_type,
            "contact_person": "Juan Dela Cruz",
            "contact_email": "juan@example.com",
            "contact_phone": "09171234567",
        }
        payload.update(overrides)
        return payload

    def _admin_payload(self, name, *, organization_type="SCHOOL", **overrides):
        payload = {
            "facility_id": self.facility.id,
            "date": self.day.isoformat(),
            "start_time": "13:00",
            "end_time": "15:00",
            "event_name": "Admin Encoded Event",
            "event_type": "OTHER",
            "purpose": "Admin encoded event",
            "expected_participants": 40,
            "items": [],
            "requester_type": "EXTERNAL",
            "organization": name,
            "organization_type": organization_type,
            "contact_person": "Maria Santos",
        }
        payload.update(overrides)
        return payload


class PublicOrganizationEntryTests(ExternalOrganizationEntryTestBase):
    def test_existing_organization_is_reused_and_official_name_kept(self):
        existing = Organization.objects.create(
            organization_name="Test Organization",
            organization_type=Organization.OrganizationType.SCHOOL_UNIVERSITY,
            contact_person="Registrar",
            contact_email="registrar@test.example",
        )

        response = self.client.post(
            PUBLIC_SUBMIT_URL, self._public_payload("  test   organization "), format="json"
        )

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(_external_organizations().count(), 1)
        reservation = Reservation.objects.get(pk=response.json()["id"])
        self.assertEqual(reservation.organization_ref_id, existing.id)
        # The registry's official spelling wins over the typed variant.
        self.assertEqual(reservation.organization, "Test Organization")

    def test_new_organization_is_created_before_the_reservation(self):
        response = self.client.post(
            PUBLIC_SUBMIT_URL, self._public_payload("Brand New Foundation"), format="json"
        )

        self.assertEqual(response.status_code, 201, response.content)
        organization = _external_organizations().get()
        self.assertEqual(organization.organization_name, "Brand New Foundation")
        self.assertEqual(
            organization.organization_type,
            Organization.OrganizationType.SCHOOL_UNIVERSITY,
        )
        # A new reservation must not verify (or otherwise privilege) the org.
        self.assertEqual(
            organization.verification_status,
            Organization.VerificationStatus.PENDING,
        )
        self.assertTrue(organization.is_active)

        reservation = Reservation.objects.get(pk=response.json()["id"])
        self.assertEqual(reservation.organization_ref_id, organization.id)

    def test_invalid_submission_does_not_create_an_organization(self):
        response = self.client.post(
            PUBLIC_SUBMIT_URL,
            self._public_payload("Should Not Exist", contact_phone="123"),
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(_external_organizations().count(), 0)
        self.assertEqual(Reservation.objects.count(), 0)

    def test_failed_reservation_creation_rolls_back_the_new_organization(self):
        with mock.patch(
            "reservations.serializers.snapshot_reservation_fees",
            side_effect=RuntimeError("fee snapshot failed"),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    PUBLIC_SUBMIT_URL,
                    self._public_payload("Rolled Back Org"),
                    format="json",
                )

        self.assertEqual(_external_organizations().count(), 0)
        self.assertEqual(Reservation.objects.count(), 0)

    def test_capitalization_variants_do_not_create_a_duplicate(self):
        first = self.client.post(
            PUBLIC_SUBMIT_URL, self._public_payload("Test Organization"), format="json"
        )
        self.assertEqual(first.status_code, 201, first.content)
        second = self.client.post(
            PUBLIC_SUBMIT_URL,
            self._public_payload(
                "TEST ORGANIZATION",
                start_time="12:00",
                end_time="14:00",
            ),
            format="json",
        )
        self.assertEqual(second.status_code, 201, second.content)

        self.assertEqual(_external_organizations().count(), 1)
        organization = _external_organizations().get()
        for response in (first, second):
            reservation = Reservation.objects.get(pk=response.json()["id"])
            self.assertEqual(reservation.organization_ref_id, organization.id)
            self.assertEqual(reservation.organization, organization.organization_name)

    def test_public_search_returns_identity_only_and_excludes_internal(self):
        Organization.objects.create(
            organization_name="Test Organization",
            organization_type=Organization.OrganizationType.NGO,
            contact_person="Director",
            contact_email="director@test.example",
        )
        internal = Organization.objects.filter(
            organization_type=Organization.OrganizationType.INTERNAL
        ).first()
        self.assertIsNotNone(internal)

        response = self.client.get(PUBLIC_ORGANIZATION_URL, {"search": "test"})

        self.assertEqual(response.status_code, 200, response.content)
        rows = response.json()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["organization_name"], "Test Organization")
        self.assertIn("organization_type_label", rows[0])
        self.assertNotIn("contact_person", rows[0])
        self.assertNotIn("contact_email", rows[0])
        self.assertNotEqual(rows[0]["id"], internal.id)

    def test_no_match_still_proceeds_without_prior_registration(self):
        response = self.client.post(
            PUBLIC_SUBMIT_URL,
            self._public_payload("Unregistered Community Group", organization_type="COMMUNITY"),
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.content)
        organization = _external_organizations().get()
        self.assertEqual(
            organization.organization_type,
            Organization.OrganizationType.COMMUNITY_ORGANIZATION,
        )
        self.assertEqual(
            organization.verification_status,
            Organization.VerificationStatus.PENDING,
        )


class AdminOrganizationEntryTests(ExternalOrganizationEntryTestBase):
    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_user(
            username="staff", password="pass12345", role=User.Role.STAFF
        )

    def test_admin_can_select_an_organization_created_by_a_public_request(self):
        auto_created = Organization.objects.create(
            organization_name="Public Created Org",
            organization_type=Organization.OrganizationType.NGO,
            contact_person="First Requester",
            contact_email="first@example.com",
            verification_status=Organization.VerificationStatus.PENDING,
        )

        self.client.force_authenticate(self.staff)
        response = self.client.post(
            RESERVATIONS_URL,
            self._admin_payload(
                auto_created.organization_name,
                organization_type="NGO",
                organization_id=auto_created.id,
            ),
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.content)
        reservation = Reservation.objects.get(pk=response.json()["id"])
        self.assertEqual(reservation.organization_ref_id, auto_created.id)
        self.assertEqual(_external_organizations().count(), 1)

    def test_admin_can_add_a_new_organization_from_the_reservation_form(self):
        self.client.force_authenticate(self.staff)
        response = self.client.post(
            RESERVATIONS_URL,
            self._admin_payload("Admin Added School", organization_type="SCHOOL"),
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.content)
        organization = _external_organizations().get()
        self.assertEqual(organization.organization_name, "Admin Added School")
        self.assertEqual(
            organization.organization_type,
            Organization.OrganizationType.SCHOOL_UNIVERSITY,
        )
        self.assertEqual(
            organization.verification_status,
            Organization.VerificationStatus.PENDING,
        )
        reservation = Reservation.objects.get(pk=response.json()["id"])
        self.assertEqual(reservation.organization_ref_id, organization.id)

    def test_admin_existing_name_is_reused_instead_of_created(self):
        existing = Organization.objects.create(
            organization_name="Test Organization",
            organization_type=Organization.OrganizationType.NGO,
            contact_person="Director",
            contact_email="director@example.com",
        )

        self.client.force_authenticate(self.staff)
        response = self.client.post(
            RESERVATIONS_URL,
            self._admin_payload(
                "test  organization",
                organization_type="NGO",
                start_time="16:00",
                end_time="18:00",
            ),
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(_external_organizations().count(), 1)
        reservation = Reservation.objects.get(pk=response.json()["id"])
        self.assertEqual(reservation.organization_ref_id, existing.id)
        self.assertEqual(reservation.organization, "Test Organization")

    def test_staff_organization_list_includes_pending_public_organizations(self):
        auto_created = Organization.objects.create(
            organization_name="Awaiting Verification",
            organization_type=Organization.OrganizationType.OTHER,
            contact_person="Requester",
            contact_email="requester@example.com",
            verification_status=Organization.VerificationStatus.PENDING,
        )

        self.client.force_authenticate(self.staff)
        response = self.client.get(ORGANIZATIONS_URL)

        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        rows = data.get("results", data)
        self.assertIn(auto_created.id, {row["id"] for row in rows})


class ExistingRecordsRemainIntactTests(ExternalOrganizationEntryTestBase):
    def test_new_submission_does_not_alter_existing_organizations_or_reservations(self):
        existing_org = Organization.objects.create(
            organization_name="Established Organization",
            organization_type=Organization.OrganizationType.NGO,
            contact_person="Director",
            contact_email="director@example.com",
        )
        existing_reservation = Reservation.objects.create(
            requester_type=Reservation.RequesterType.EXTERNAL,
            organization="Established Organization",
            organization_ref=existing_org,
            contact_person="Director",
            contact_email="director@example.com",
            event_name="Earlier Event",
            facility=self.facility,
            date=self.day,
            start_time=time(6, 0),
            end_time=time(8, 0),
        )
        original_code = existing_org.organization_code

        response = self.client.post(
            PUBLIC_SUBMIT_URL,
            self._public_payload("Another Organization"),
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.content)
        existing_org.refresh_from_db()
        existing_reservation.refresh_from_db()
        self.assertEqual(existing_org.organization_code, original_code)
        self.assertEqual(existing_org.organization_name, "Established Organization")
        self.assertEqual(existing_reservation.organization_ref_id, existing_org.id)
        self.assertEqual(_external_organizations().count(), 2)


class InternalOrganizationEntryUnchangedTests(ExternalOrganizationEntryTestBase):
    def test_public_internal_submission_still_requires_a_registered_internal_org(self):
        internal = Organization.objects.filter(
            organization_type=Organization.OrganizationType.INTERNAL,
            is_active=True,
        ).first()
        self.assertIsNotNone(internal)

        response = self.client.post(
            PUBLIC_SUBMIT_URL,
            self._public_payload(
                internal.organization_name,
                organization_type="",
                requester_type="CAMPUS",
                organization_id=internal.id,
            ),
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.content)
        reservation = Reservation.objects.get(pk=response.json()["id"])
        self.assertEqual(reservation.organization_ref_id, internal.id)
        self.assertEqual(reservation.requester_type, Reservation.RequesterType.CAMPUS)
        self.assertEqual(_external_organizations().count(), 0)
