"""External-organization reservation rules.

Covers the guarantees from the task's reservation-restrictions section:
an Approved organization books through the normal workflow, while Pending,
Rejected, and Suspended organizations cannot create reservations at all —
and the organization is always resolved from the authenticated profile, never
from the request body.
"""

from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Organization
from facilities.models import Facility, OperatingHour
from .models import PricingRule, Reservation

User = get_user_model()

RESERVATIONS_URL = "/api/reservations/"
AVAILABILITY_URL = "/api/availability/check/"


def _make_organization(status, name="ABC Foundation"):
    return Organization.objects.create(
        organization_name=name,
        organization_type=Organization.OrganizationType.NGO,
        contact_person="Juan Dela Cruz",
        contact_email="juan@abcfoundation.org",
        contact_number="09171234567",
        verification_status=status,
    )


class ExternalOrganizationReservationTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.approved_org = _make_organization(Organization.VerificationStatus.APPROVED)
        self.pending_org = _make_organization(
            Organization.VerificationStatus.PENDING, name="Pending Org"
        )
        self.rejected_org = _make_organization(
            Organization.VerificationStatus.REJECTED, name="Rejected Org"
        )
        self.suspended_org = _make_organization(
            Organization.VerificationStatus.SUSPENDED, name="Suspended Org"
        )

        self.member = self._external_user("juan", self.approved_org)
        self.pending_member = self._external_user("maria", self.pending_org)
        self.rejected_member = self._external_user("pedro", self.rejected_org)
        self.suspended_member = self._external_user("ana", self.suspended_org)

        self.campus_user = User.objects.create_user(
            username="campus", password="pass12345", role=User.Role.REQUESTER
        )
        self.staff = User.objects.create_user(
            username="staff", password="pass12345", role=User.Role.STAFF
        )

        self.facility = Facility.objects.create(
            name="Gymnasium",
            facility_type=Facility.FacilityType.GYMNASIUM,
            capacity=300,
        )
        OperatingHour.objects.create(
            facility=self.facility,
            day_of_week=0,
            open_time=time(6, 0),
            close_time=time(22, 0),
        )
        # Near-future Monday matching the operating hours above.
        self.day = timezone.localdate() + timedelta(days=1)
        while self.day.weekday() != 0:
            self.day += timedelta(days=1)

    def _external_user(self, username, organization):
        user = User.objects.create_user(
            username=username,
            password="pass12345",
            role=User.Role.REQUESTER,
            first_name=username.title(),
            email=f"{username}@abcfoundation.org",
        )
        user.affiliation = User.Affiliation.EXTERNAL_ORGANIZATION
        user.organization_ref = organization
        user.save(update_fields=["affiliation", "organization_ref"])
        return user

    def _payload(self, **overrides):
        payload = {
            "facility_id": self.facility.id,
            "date": self.day.isoformat(),
            "start_time": "13:00",
            "end_time": "16:00",
            "event_name": "Community Seminar",
            "event_type": "SEMINAR",
            "purpose": "Community Seminar",
            "expected_participants": 80,
            "items": [],
        }
        payload.update(overrides)
        return payload

    # -- Approved organizations book normally ---------------------------

    def test_approved_member_creates_external_reservation(self):
        """The requester type is derived from the profile, not the payload."""
        self.client.force_authenticate(self.member)
        response = self.client.post(RESERVATIONS_URL, self._payload(), format="json")
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()

        self.assertEqual(body["requester_type"], "EXTERNAL")
        self.assertEqual(body["requester"], self.member.display_name)
        self.assertEqual(body["affiliation"], "EXTERNAL_ORGANIZATION")
        self.assertEqual(body["affiliation_label"], "External Organization")
        self.assertEqual(body["organization"], "ABC Foundation")
        self.assertEqual(body["organization_code"], "EXT-0001")
        self.assertEqual(body["organization_type"], "NGO")
        # Still enters the normal pending review queue (no special privilege).
        self.assertEqual(body["status"], "PENDING")

        reservation = Reservation.objects.get(pk=body["id"])
        self.assertEqual(reservation.requester, self.member)
        self.assertEqual(reservation.created_by, self.member)
        self.assertEqual(reservation.organization_ref, self.approved_org)

    def test_member_cannot_spoof_organization_fields(self):
        """Organization details in the body are ignored in favor of the profile."""
        self.client.force_authenticate(self.member)
        response = self.client.post(
            RESERVATIONS_URL,
            self._payload(
                organization="Some Other Foundation",
                organization_type="GOVERNMENT",
                organization_ref=self.pending_org.id,
                requester_type="CAMPUS",
                contact_person="Someone Else",
                contact_email="attacker@example.com",
            ),
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        reservation = Reservation.objects.get(pk=response.json()["id"])
        self.assertEqual(reservation.organization_ref, self.approved_org)
        self.assertEqual(reservation.organization, "ABC Foundation")
        self.assertEqual(reservation.organization_type, "NGO")
        self.assertEqual(reservation.requester_type, "EXTERNAL")
        self.assertEqual(reservation.contact_person, "Someone Else")

    def test_contact_details_fall_back_to_profile(self):
        self.client.force_authenticate(self.member)
        response = self.client.post(RESERVATIONS_URL, self._payload(), format="json")
        self.assertEqual(response.status_code, 201, response.content)
        reservation = Reservation.objects.get(pk=response.json()["id"])
        self.assertEqual(reservation.contact_person, self.member.display_name)
        self.assertEqual(reservation.contact_email, "juan@abcfoundation.org")

    # -- Unverified organizations are blocked ---------------------------

    def test_pending_organization_cannot_reserve(self):
        self.client.force_authenticate(self.pending_member)
        response = self.client.post(RESERVATIONS_URL, self._payload(), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("pending", str(response.json()).lower())
        self.assertEqual(Reservation.objects.count(), 0)

    def test_rejected_organization_cannot_reserve(self):
        self.client.force_authenticate(self.rejected_member)
        response = self.client.post(RESERVATIONS_URL, self._payload(), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("rejected", str(response.json()).lower())
        self.assertEqual(Reservation.objects.count(), 0)

    def test_suspended_organization_cannot_reserve(self):
        self.client.force_authenticate(self.suspended_member)
        response = self.client.post(RESERVATIONS_URL, self._payload(), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("suspended", str(response.json()).lower())
        self.assertEqual(Reservation.objects.count(), 0)

    def test_approving_organization_unblocks_reservations(self):
        self.pending_org.verification_status = Organization.VerificationStatus.APPROVED
        self.pending_org.save(update_fields=["verification_status"])
        self.client.force_authenticate(self.pending_member)
        response = self.client.post(RESERVATIONS_URL, self._payload(), format="json")
        self.assertEqual(response.status_code, 201, response.content)

    # -- Existing behavior preserved -------------------------------------

    def test_campus_user_still_cannot_claim_external_type(self):
        self.client.force_authenticate(self.campus_user)
        response = self.client.post(
            RESERVATIONS_URL,
            self._payload(
                requester_type="EXTERNAL",
                organization="ABC National High School",
                organization_type="SCHOOL",
                contact_person="Juan Dela Cruz",
                contact_email="juan@example.com",
            ),
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("requester_type", response.json())

    def test_campus_reservation_unchanged(self):
        self.client.force_authenticate(self.campus_user)
        response = self.client.post(RESERVATIONS_URL, self._payload(), format="json")
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["requester_type"], "CAMPUS")
        self.assertEqual(body["affiliation_label"], "Campus User")
        self.assertEqual(body["organization_code"], "")

    def test_staff_external_reservation_without_account_still_works(self):
        self.client.force_authenticate(self.staff)
        response = self.client.post(
            RESERVATIONS_URL,
            self._payload(
                requester_type="EXTERNAL",
                organization="ABC National High School",
                organization_type="SCHOOL",
                contact_person="Juan Dela Cruz",
                contact_email="juan@example.com",
            ),
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["requester_type"], "EXTERNAL")
        self.assertEqual(body["requester"], "ABC National High School")
        self.assertEqual(body["organization_code"], "")
        reservation = Reservation.objects.get(pk=body["id"])
        self.assertIsNone(reservation.organization_ref)

    # -- Pricing follows the trusted affiliation --------------------------

    def test_availability_pricing_is_external_for_approved_member(self):
        PricingRule.objects.create(
            fee_type=PricingRule.FeeType.FACILITY,
            facility_type=Facility.FacilityType.GYMNASIUM,
            unit=PricingRule.Unit.FLAT,
            unit_price="5000.00",
            label="Gymnasium",
        )
        self.client.force_authenticate(self.member)
        response = self.client.post(
            AVAILABILITY_URL,
            {
                "facility_id": self.facility.id,
                "date": self.day.isoformat(),
                "start_time": "13:00",
                "end_time": "16:00",
                "items": [],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        pricing = response.json()["pricing"]
        self.assertTrue(pricing["external"])
        self.assertEqual(pricing["requester_type"], "EXTERNAL")
        self.assertEqual(pricing["total"], "5000.00")

    def test_availability_pricing_not_external_for_pending_member(self):
        PricingRule.objects.create(
            fee_type=PricingRule.FeeType.FACILITY,
            facility_type=Facility.FacilityType.GYMNASIUM,
            unit=PricingRule.Unit.FLAT,
            unit_price="5000.00",
        )
        self.client.force_authenticate(self.pending_member)
        response = self.client.post(
            AVAILABILITY_URL,
            {
                "facility_id": self.facility.id,
                "date": self.day.isoformat(),
                "start_time": "13:00",
                "end_time": "16:00",
                "items": [],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["pricing"]["external"])

    def test_availability_pricing_unchanged_for_campus_user(self):
        PricingRule.objects.create(
            fee_type=PricingRule.FeeType.FACILITY,
            facility_type=Facility.FacilityType.GYMNASIUM,
            unit=PricingRule.Unit.FLAT,
            unit_price="5000.00",
        )
        self.client.force_authenticate(self.campus_user)
        response = self.client.post(
            AVAILABILITY_URL,
            {
                "facility_id": self.facility.id,
                "date": self.day.isoformat(),
                "start_time": "13:00",
                "end_time": "16:00",
                "items": [],
                "requester_type": "EXTERNAL",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["pricing"]["external"])

    # -- Cross-organization isolation -------------------------------------

    def test_member_only_sees_own_reservations(self):
        other_member = self._external_user("other", self.approved_org)
        other = Reservation.objects.create(
            requester=other_member,
            requester_type=Reservation.RequesterType.EXTERNAL,
            organization_ref=self.approved_org,
            organization="ABC Foundation",
            event_name="Someone else's event",
            facility=self.facility,
            date=self.day,
            start_time=time(8, 0),
            end_time=time(10, 0),
        )
        mine = Reservation.objects.create(
            requester=self.member,
            requester_type=Reservation.RequesterType.EXTERNAL,
            organization_ref=self.approved_org,
            organization="ABC Foundation",
            event_name="My event",
            facility=self.facility,
            date=self.day,
            start_time=time(10, 0),
            end_time=time(12, 0),
        )

        self.client.force_authenticate(self.member)
        response = self.client.get(RESERVATIONS_URL)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        results = data.get("results", data)
        ids = {row["id"] for row in results}
        self.assertIn(mine.id, ids)
        self.assertNotIn(other.id, ids)

    def test_requester_cannot_retrieve_another_users_reservation(self):
        other_member = self._external_user("other", self.approved_org)
        other = Reservation.objects.create(
            requester=other_member,
            requester_type=Reservation.RequesterType.EXTERNAL,
            organization_ref=self.approved_org,
            event_name="Private",
            facility=self.facility,
            date=self.day,
            start_time=time(8, 0),
            end_time=time(10, 0),
        )
        self.client.force_authenticate(self.member)
        response = self.client.get(f"{RESERVATIONS_URL}{other.id}/")
        self.assertEqual(response.status_code, 404)


class AffiliationSnapshotTests(TestCase):
    """The affiliation label is resolved from the requester's live profile."""

    def test_affiliation_label_reflects_profile(self):
        user = User.objects.create_user(
            username="staffmember", password="pass12345", role=User.Role.REQUESTER
        )
        facility = Facility.objects.create(name="AVR", facility_type=Facility.FacilityType.AVR)
        reservation = Reservation.objects.create(
            requester=user,
            event_name="Legacy event",
            facility=facility,
            date=timezone.localdate() + timedelta(days=3),
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
        # Blank affiliation (legacy account) reads as a campus user.
        self.assertEqual(reservation.affiliation, "")
        self.assertEqual(reservation.affiliation_label, "Campus User")
        self.assertEqual(reservation.organization_code, "")

        user.affiliation = User.Affiliation.NORSU_FACULTY_STAFF
        user.save(update_fields=["affiliation"])
        reservation.refresh_from_db()
        self.assertEqual(reservation.affiliation_label, "NORSU Faculty/Staff")
