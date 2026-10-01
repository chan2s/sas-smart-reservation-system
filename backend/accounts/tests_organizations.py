"""Tests for the organization affiliation layer.

These cover the affiliation/registration/verification API — both the external
organizations and the nine managed INTERNAL campus organizations — and the
guarantees that the feature is additive: existing (legacy) users keep working
exactly as before, and nothing about the organization model is reachable from
the client in a way that could be tampered with.
"""

from io import StringIO

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.management.commands.seed import Command as SeedCommand
from accounts.models import AuditLog, Organization

User = get_user_model()

AFFILIATION_URL = "/api/auth/affiliation/"
ORGANIZATIONS_URL = "/api/auth/organizations/"
INTERNAL_ORGANIZATIONS_URL = "/api/auth/internal-organizations/"


def _rows(payload):
    """List endpoints are paginated project-wide — unwrap the page when so."""
    if isinstance(payload, dict) and "results" in payload:
        return payload["results"]
    return payload


def _external_organizations():
    """External organizations only.

    Nine managed INTERNAL organizations are seeded by migration, so tests
    that count "organizations" must exclude them to stay meaningful.
    """
    return Organization.objects.exclude(
        organization_type=Organization.OrganizationType.INTERNAL
    )


def _organization_payload(**overrides):
    payload = {
        "affiliation": "EXTERNAL_ORGANIZATION",
        "organization_name": "ABC Foundation",
        "organization_type": "NGO",
        "contact_person": "Juan Dela Cruz",
        "contact_email": "juan@abcfoundation.org",
        "contact_number": "09171234567",
        "address": "123 Rizal St, Dumaguete",
        "purpose": "Community Seminar",
    }
    payload.update(overrides)
    return payload


class AffiliationApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="juan",
            password="pass12345",
            role=User.Role.REQUESTER,
            first_name="Juan",
            last_name="Dela Cruz",
            email="juan@example.com",
        )

    # -- Backward compatibility ----------------------------------------

    def test_legacy_account_is_unaffiliated_and_fully_usable(self):
        """Existing accounts must behave exactly as before the feature."""
        self.assertEqual(self.user.affiliation, "")
        self.assertFalse(self.user.has_affiliation)
        self.assertFalse(self.user.is_external_organization)
        self.assertTrue(self.user.can_create_reservations)
        self.assertEqual(self.user.reservation_block_reason, "")

    def test_patch_me_cannot_set_affiliation_or_organization_ref(self):
        """Affiliation is never writable through the generic profile PATCH."""
        other = Organization.objects.create(
            organization_name="Ghost Org",
            organization_type=Organization.OrganizationType.OTHER,
            contact_person="Nobody",
            contact_email="nobody@example.com",
        )
        self.client.force_authenticate(self.user)
        response = self.client.patch(
            "/api/auth/me/",
            {
                "affiliation": "EXTERNAL_ORGANIZATION",
                "organization_ref": other.id,
                "organization": "Student Affairs",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.user.refresh_from_db()
        self.assertEqual(self.user.affiliation, "")
        self.assertIsNone(self.user.organization_ref)
        # The free-text field remains editable (unchanged legacy behavior).
        self.assertEqual(self.user.organization, "Student Affairs")

    # -- Authentication -------------------------------------------------

    def test_affiliation_requires_authentication(self):
        self.assertEqual(self.client.get(AFFILIATION_URL).status_code, 401)
        self.assertEqual(
            self.client.post(
                AFFILIATION_URL, {"affiliation": "NORSU_FACULTY_STAFF"}, format="json"
            ).status_code,
            401,
        )

    # -- Internal affiliations ------------------------------------------

    def test_set_norsu_affiliation(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            AFFILIATION_URL,
            {"affiliation": "NORSU_FACULTY_STAFF", "organization": "College of Engineering"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["affiliation"], "NORSU_FACULTY_STAFF")
        self.assertEqual(body["affiliation_label"], "NORSU Faculty/Staff")
        self.assertTrue(body["has_affiliation"])
        self.assertIsNone(body["organization"])
        self.assertTrue(body["can_create_reservations"])

        self.user.refresh_from_db()
        self.assertEqual(self.user.affiliation, "NORSU_FACULTY_STAFF")
        self.assertEqual(self.user.organization, "College of Engineering")
        self.assertIsNone(self.user.organization_ref)
        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.user, action=AuditLog.Action.AFFILIATION_CHANGED
            ).exists()
        )

    # -- External organization registration ------------------------------

    def test_external_registration_creates_pending_organization(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            AFFILIATION_URL, _organization_payload(), format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()

        organization = Organization.objects.get(organization_name="ABC Foundation")
        self.assertEqual(organization.organization_code, "EXT-0001")
        self.assertEqual(
            organization.verification_status, Organization.VerificationStatus.PENDING
        )
        self.assertEqual(organization.created_by, self.user)
        self.assertEqual(body["organization_verification_status"], "PENDING")
        self.assertFalse(body["can_create_reservations"])
        self.assertIn("pending", body["reservation_block_reason"].lower())

        self.user.refresh_from_db()
        self.assertEqual(self.user.affiliation, "EXTERNAL_ORGANIZATION")
        self.assertEqual(self.user.organization_ref, organization)
        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.user, action=AuditLog.Action.ORGANIZATION_REGISTERED
            ).exists()
        )

    def test_external_registration_requires_core_contact_fields(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            AFFILIATION_URL,
            {"affiliation": "EXTERNAL_ORGANIZATION"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(_external_organizations().count(), 0)

    def test_organization_codes_are_sequential_and_unique(self):
        first = Organization.objects.create(
            organization_name="One",
            organization_type=Organization.OrganizationType.OTHER,
            contact_person="A",
            contact_email="a@example.com",
        )
        second = Organization.objects.create(
            organization_name="Two",
            organization_type=Organization.OrganizationType.OTHER,
            contact_person="B",
            contact_email="b@example.com",
        )
        self.assertEqual(first.organization_code, "EXT-0001")
        self.assertEqual(second.organization_code, "EXT-0002")
        self.assertEqual(_external_organizations().count(), 2)

    def test_members_cannot_re_affiliate_out_of_an_organization(self):
        """A pending org member cannot escape the block by switching to NORSU."""
        self.client.force_authenticate(self.user)
        self.client.post(AFFILIATION_URL, _organization_payload(), format="json")
        response = self.client.post(
            AFFILIATION_URL, {"affiliation": "NORSU_FACULTY_STAFF"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.affiliation, "EXTERNAL_ORGANIZATION")

    def test_resubmitting_updates_same_organization_without_duplicating(self):
        self.client.force_authenticate(self.user)
        self.client.post(AFFILIATION_URL, _organization_payload(), format="json")
        self.user.refresh_from_db()
        response = self.client.post(
            AFFILIATION_URL,
            _organization_payload(contact_number="09999999999"),
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(_external_organizations().count(), 1)
        organization = Organization.objects.get(organization_name="ABC Foundation")
        self.assertEqual(organization.contact_number, "09999999999")

    def test_rejected_organization_resubmission_returns_to_pending(self):
        self.client.force_authenticate(self.user)
        self.client.post(AFFILIATION_URL, _organization_payload(), format="json")
        organization = Organization.objects.get(organization_name="ABC Foundation")
        organization.verification_status = Organization.VerificationStatus.REJECTED
        organization.review_notes = "Incomplete documents"
        organization.save()
        # A real request re-loads the user (and its organization) from the
        # database, so drop the in-memory copy before the next call.
        self.user.refresh_from_db()

        response = self.client.post(
            AFFILIATION_URL, _organization_payload(), format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        organization.refresh_from_db()
        self.assertEqual(
            organization.verification_status, Organization.VerificationStatus.PENDING
        )
        self.assertEqual(organization.review_notes, "")
        self.assertIsNone(organization.reviewed_at)

    def test_suspended_organization_cannot_be_edited(self):
        self.client.force_authenticate(self.user)
        self.client.post(AFFILIATION_URL, _organization_payload(), format="json")
        organization = Organization.objects.get(organization_name="ABC Foundation")
        organization.verification_status = Organization.VerificationStatus.SUSPENDED
        organization.save()
        self.user.refresh_from_db()

        response = self.client.post(
            AFFILIATION_URL, _organization_payload(), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("suspended", response.json()["detail"].lower())

    def test_organization_reads_only_own_record(self):
        """GET returns the caller's organization and nothing else."""
        other = Organization.objects.create(
            organization_name="Other Org",
            organization_type=Organization.OrganizationType.OTHER,
            contact_person="X",
            contact_email="x@example.com",
        )
        self.client.force_authenticate(self.user)
        self.client.post(AFFILIATION_URL, _organization_payload(), format="json")

        body = self.client.get(AFFILIATION_URL).json()
        self.assertEqual(body["organization"]["organization_name"], "ABC Foundation")
        self.assertNotEqual(body["organization"]["id"], other.id)

    def test_multiple_users_can_share_one_organization(self):
        """Organization 1 → Many Users; each user has their own account."""
        self.client.force_authenticate(self.user)
        self.client.post(AFFILIATION_URL, _organization_payload(), format="json")
        organization = Organization.objects.get(organization_name="ABC Foundation")

        colleague = User.objects.create_user(
            username="maria", password="pass12345", role=User.Role.REQUESTER
        )
        colleague.affiliation = User.Affiliation.EXTERNAL_ORGANIZATION
        colleague.organization_ref = organization
        colleague.save(update_fields=["affiliation", "organization_ref"])

        self.assertEqual(organization.members.count(), 2)
        self.assertEqual(organization.member_count, 2)
        self.assertNotEqual(self.user.pk, colleague.pk)


class OrganizationVerificationApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.staff = User.objects.create_user(
            username="staff", password="pass12345", role=User.Role.STAFF
        )
        self.requester = User.objects.create_user(
            username="requester", password="pass12345", role=User.Role.REQUESTER
        )
        self.organization = Organization.objects.create(
            organization_name="ABC Foundation",
            organization_type=Organization.OrganizationType.NGO,
            contact_person="Juan Dela Cruz",
            contact_email="juan@abcfoundation.org",
        )
        self.requester.affiliation = User.Affiliation.EXTERNAL_ORGANIZATION
        self.requester.organization_ref = self.organization
        self.requester.save(update_fields=["affiliation", "organization_ref"])

    def test_requesters_cannot_reach_staff_endpoints(self):
        self.client.force_authenticate(self.requester)
        self.assertEqual(self.client.get(ORGANIZATIONS_URL).status_code, 403)
        self.assertEqual(
            self.client.get(f"{ORGANIZATIONS_URL}{self.organization.pk}/").status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                f"{ORGANIZATIONS_URL}{self.organization.pk}/verify/",
                {"action": "approve"},
                format="json",
            ).status_code,
            403,
        )

    def test_staff_can_list_and_filter_pending_organizations(self):
        self.client.force_authenticate(self.staff)
        response = self.client.get(f"{ORGANIZATIONS_URL}?status=PENDING")
        self.assertEqual(response.status_code, 200)
        rows = _rows(response.json())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["organization_code"], "EXT-0001")
        self.assertEqual(rows[0]["member_count"], 1)

        approved = _rows(self.client.get(f"{ORGANIZATIONS_URL}?status=APPROVED").json())
        self.assertEqual(approved, [])

    def test_staff_detail_lists_members(self):
        self.client.force_authenticate(self.staff)
        response = self.client.get(f"{ORGANIZATIONS_URL}{self.organization.pk}/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["members"][0]["username"], "requester")
        self.assertEqual(body["members"][0]["affiliation_label"], "External Organization")

    def test_approve_reactivate_and_suspend(self):
        self.client.force_authenticate(self.staff)

        response = self.client.post(
            f"{ORGANIZATIONS_URL}{self.organization.pk}/verify/",
            {"action": "approve", "notes": "Documents complete."},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["verification_status"], "APPROVED")
        self.requester.refresh_from_db()
        self.assertTrue(self.requester.can_create_reservations)

        response = self.client.post(
            f"{ORGANIZATIONS_URL}{self.organization.pk}/verify/",
            {"action": "suspend", "notes": "Policy violation."},
            format="json",
        )
        self.assertEqual(response.json()["verification_status"], "SUSPENDED")
        self.requester.refresh_from_db()
        self.assertFalse(self.requester.can_create_reservations)

        response = self.client.post(
            f"{ORGANIZATIONS_URL}{self.organization.pk}/verify/",
            {"action": "reactivate"},
            format="json",
        )
        self.assertEqual(response.json()["verification_status"], "APPROVED")
        self.requester.refresh_from_db()
        self.assertTrue(self.requester.can_create_reservations)

    def test_reject_blocks_reservations(self):
        self.client.force_authenticate(self.staff)
        response = self.client.post(
            f"{ORGANIZATIONS_URL}{self.organization.pk}/verify/",
            {"action": "reject", "notes": "Invalid registration."},
            format="json",
        )
        self.assertEqual(response.json()["verification_status"], "REJECTED")
        self.requester.refresh_from_db()
        self.assertFalse(self.requester.can_create_reservations)
        self.assertIn("rejected", self.requester.reservation_block_reason.lower())

    def test_verification_is_audited(self):
        self.client.force_authenticate(self.staff)
        self.client.post(
            f"{ORGANIZATIONS_URL}{self.organization.pk}/verify/",
            {"action": "approve"},
            format="json",
        )
        entry = AuditLog.objects.filter(
            action=AuditLog.Action.ORGANIZATION_APPROVED
        ).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.actor, self.staff)
        self.assertEqual(entry.object_id, str(self.organization.pk))

    def test_unknown_action_and_missing_organization(self):
        self.client.force_authenticate(self.staff)
        self.assertEqual(
            self.client.post(
                f"{ORGANIZATIONS_URL}{self.organization.pk}/verify/",
                {"action": "obliterate"},
                format="json",
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                f"{ORGANIZATIONS_URL}99999/verify/",
                {"action": "approve"},
                format="json",
            ).status_code,
            404,
        )


REGISTER_URL = "/api/auth/register/"
LOGIN_URL = "/api/auth/login/"


def _external_registration(**overrides):
    payload = {
        "username": "bnhs",
        "password": "pass12345",
        "first_name": "Juan",
        "last_name": "Dela Cruz",
        "email": "juan@bnhs.edu.ph",
        "affiliation": "EXTERNAL_ORGANIZATION",
        "organization_name": "Bayawan National High School",
        "organization_type": "SCHOOL_UNIVERSITY",
        "contact_person": "Juan Dela Cruz",
        "contact_email": "office@bnhs.edu.ph",
        "contact_number": "09171234567",
        "address": "Bayawan City",
        "purpose": "Community sports event",
    }
    payload.update(overrides)
    return payload


class ExternalOrganizationRegistrationTests(TestCase):
    """Sign-up must create the org as PENDING and must NOT authenticate."""

    def setUp(self):
        self.client = APIClient()

    def test_external_registration_creates_pending_organization(self):
        response = self.client.post(REGISTER_URL, _external_registration(), format="json")
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()

        # Registration issues no credentials — the SPA must send the new user
        # to the login page.
        self.assertNotIn("access", body)
        self.assertNotIn("refresh", body)

        organization = Organization.objects.get(organization_name="Bayawan National High School")
        self.assertEqual(organization.organization_code, "EXT-0001")
        self.assertEqual(
            organization.verification_status, Organization.VerificationStatus.PENDING
        )
        self.assertEqual(organization.organization_type, "SCHOOL_UNIVERSITY")

        user = User.objects.get(username="bnhs")
        self.assertEqual(user.affiliation, User.Affiliation.EXTERNAL_ORGANIZATION)
        self.assertEqual(user.organization_ref, organization)
        # A member of an unverified org is blocked from reserving.
        self.assertFalse(user.can_create_reservations)
        self.assertTrue(
            AuditLog.objects.filter(
                actor=user, action=AuditLog.Action.ORGANIZATION_REGISTERED
            ).exists()
        )

    def test_external_registration_missing_fields_rejected(self):
        for field in (
            "organization_name",
            "contact_person",
            "contact_email",
            "organization_type",
        ):
            payload = _external_registration()
            payload.pop(field)
            response = self.client.post(REGISTER_URL, payload, format="json")
            self.assertEqual(response.status_code, 400, (field, response.content))
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(_external_organizations().count(), 0)

    def test_new_external_user_can_log_in_and_is_still_blocked(self):
        self.client.post(REGISTER_URL, _external_registration(), format="json")
        response = self.client.post(
            LOGIN_URL, {"username": "bnhs", "password": "pass12345"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertIn("access", body)
        self.assertFalse(body["user"]["can_create_reservations"])
        self.assertEqual(body["user"]["organization_verification_status"], "PENDING")

    def test_internal_registration_unchanged(self):
        response = self.client.post(
            REGISTER_URL,
            {
                "username": "campusnew",
                "password": "pass12345",
                "first_name": "Maria",
                "last_name": "Santos",
                "email": "maria@norsu.edu.ph",
                "affiliation": "NORSU_FACULTY_STAFF",
                "organization": "College of Engineering",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(_external_organizations().count(), 0)
        user = User.objects.get(username="campusnew")
        self.assertEqual(user.affiliation, User.Affiliation.NORSU_FACULTY_STAFF)
        self.assertEqual(user.organization, "College of Engineering")
        self.assertIsNone(user.organization_ref)
        self.assertTrue(user.can_create_reservations)


class InternalOrganizationTests(TestCase):
    """The nine managed INTERNAL campus organizations.

    Covers the data migration/seed, the public picker, registration and
    affiliation linkage, spoof-prevention, and staff management. Internal
    requesters must always read as CAMPUS (never external pricing), and an
    external registration must never be able to claim an internal org.
    """

    def setUp(self):
        self.client = APIClient()
        self.internal = Organization.objects.get(organization_code="CAS")
        self.staff = User.objects.create_user(
            username="staff", password="pass12345", role=User.Role.STAFF
        )

    def _internal_user(self, username="faculty"):
        user = User.objects.create_user(
            username=username, password="pass12345", role=User.Role.REQUESTER
        )
        user.affiliation = User.Affiliation.NORSU_FACULTY_STAFF
        user.organization_ref = self.internal
        user.save(update_fields=["affiliation", "organization_ref"])
        return user

    # -- Seeded data ----------------------------------------------------

    def test_all_nine_internal_organizations_are_seeded_active(self):
        self.assertEqual(len(Organization.INTERNAL_ORGANIZATIONS), 9)
        for code, name in Organization.INTERNAL_ORGANIZATIONS:
            organization = Organization.objects.get(organization_code=code)
            self.assertEqual(
                organization.organization_type,
                Organization.OrganizationType.INTERNAL,
            )
            self.assertEqual(
                organization.verification_status,
                Organization.VerificationStatus.APPROVED,
            )
            self.assertTrue(organization.is_active)
            self.assertTrue(organization.is_internal)
            self.assertEqual(organization.acronym, code)
            self.assertEqual(organization.organization_name, name)
            self.assertTrue(organization.is_verified)

    def test_display_name_and_status_label(self):
        self.assertEqual(self.internal.display_name, "CAS — College of Arts and Sciences")
        self.assertEqual(self.internal.status_label, "Approved")
        care = Organization.objects.get(organization_code="CARE")
        # No expanded name was provided, so CARE stands alone.
        self.assertEqual(care.display_name, "CARE")

    def test_seeding_is_idempotent(self):
        SeedCommand(stdout=StringIO()).seed_organizations()
        SeedCommand(stdout=StringIO()).seed_organizations()
        self.assertEqual(
            Organization.objects.filter(
                organization_type=Organization.OrganizationType.INTERNAL
            ).count(),
            9,
        )

    # -- Public picker --------------------------------------------------

    def test_public_list_returns_only_active_internal_organizations(self):
        response = self.client.get(INTERNAL_ORGANIZATIONS_URL)
        self.assertEqual(response.status_code, 200)
        rows = _rows(response.json())
        self.assertEqual(len(rows), 9)
        self.assertEqual(
            {row["acronym"] for row in rows},
            {code for code, _ in Organization.INTERNAL_ORGANIZATIONS},
        )
        self.assertTrue(all("display_name" in row for row in rows))

        # An inactive organization disappears from the picker.
        self.internal.is_active = False
        self.internal.save(update_fields=["is_active"])
        rows = _rows(self.client.get(INTERNAL_ORGANIZATIONS_URL).json())
        self.assertEqual(len(rows), 8)

    # -- Registration and affiliation -----------------------------------

    def test_registration_links_internal_organization(self):
        response = self.client.post(
            REGISTER_URL,
            {
                "username": "newstudent",
                "password": "pass12345",
                "first_name": "Maria",
                "last_name": "Santos",
                "email": "maria@norsu.edu.ph",
                "affiliation": "NORSU_FACULTY_STAFF",
                "organization_id": self.internal.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        user = User.objects.get(username="newstudent")
        self.assertEqual(user.organization_ref, self.internal)
        self.assertTrue(user.can_create_reservations)
        # Internal organizations never price as external.
        self.assertEqual(user.trusted_requester_type, "CAMPUS")

    def test_registration_rejects_inactive_internal_organization(self):
        self.internal.is_active = False
        self.internal.save(update_fields=["is_active"])
        response = self.client.post(
            REGISTER_URL,
            {
                "username": "newstudent",
                "password": "pass12345",
                "first_name": "Maria",
                "last_name": "Santos",
                "email": "maria@norsu.edu.ph",
                "affiliation": "NORSU_FACULTY_STAFF",
                "organization_id": self.internal.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(User.objects.filter(username="newstudent").exists())

    def test_affiliation_endpoint_links_internal_organization(self):
        user = User.objects.create_user(
            username="campus", password="pass12345", role=User.Role.REQUESTER
        )
        self.client.force_authenticate(user)
        response = self.client.post(
            AFFILIATION_URL,
            {"affiliation": "NORSU_FACULTY_STAFF", "organization_id": self.internal.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        user.refresh_from_db()
        self.assertEqual(user.organization_ref, self.internal)

    def test_affiliation_rejects_an_external_organization_id(self):
        external = Organization.objects.create(
            organization_name="ABC Foundation",
            organization_type=Organization.OrganizationType.NGO,
            contact_person="Juan Dela Cruz",
            contact_email="juan@abcfoundation.org",
        )
        user = User.objects.create_user(
            username="campus", password="pass12345", role=User.Role.REQUESTER
        )
        self.client.force_authenticate(user)
        response = self.client.post(
            AFFILIATION_URL,
            {"affiliation": "NORSU_FACULTY_STAFF", "organization_id": external.id},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        user.refresh_from_db()
        self.assertIsNone(user.organization_ref_id)

    # -- Spoof prevention ------------------------------------------------

    def test_internal_user_cannot_inject_an_external_organization(self):
        """A client-supplied type/name is ignored for internal affiliations."""
        response = self.client.post(
            REGISTER_URL,
            {
                "username": "spoofer",
                "password": "pass12345",
                "first_name": "Eve",
                "last_name": "Spoof",
                "email": "eve@norsu.edu.ph",
                "affiliation": "NORSU_FACULTY_STAFF",
                "organization_id": self.internal.id,
                "organization_name": "Fake NGO",
                "organization_type": "NGO",
                "contact_person": "Eve",
                "contact_email": "eve@fake.org",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        user = User.objects.get(username="spoofer")
        self.assertEqual(user.organization_ref, self.internal)
        self.assertEqual(_external_organizations().count(), 0)

    def test_external_registration_cannot_claim_an_internal_organization(self):
        response = self.client.post(
            REGISTER_URL,
            _external_registration(organization_id=self.internal.id),
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        user = User.objects.get(username="bnhs")
        self.assertNotEqual(user.organization_ref_id, self.internal.id)
        self.assertFalse(user.organization_ref.is_internal)
        self.assertEqual(user.organization_ref.organization_type, "SCHOOL_UNIVERSITY")

    # -- Reservation gating ----------------------------------------------

    def test_deactivated_internal_organization_blocks_reservations(self):
        user = self._internal_user()
        self.assertTrue(user.can_create_reservations)
        self.internal.is_active = False
        self.internal.save(update_fields=["is_active"])
        # Re-fetch so the linked organization is not served from cache.
        user = User.objects.get(pk=user.pk)
        self.assertFalse(user.can_create_reservations)
        self.assertTrue(user.reservation_block_reason)

    # -- Staff management ------------------------------------------------

    def test_staff_listing_hides_internal_organizations_by_default(self):
        self.client.force_authenticate(self.staff)
        self.assertEqual(_rows(self.client.get(ORGANIZATIONS_URL).json()), [])
        rows = _rows(self.client.get(f"{ORGANIZATIONS_URL}?type=INTERNAL").json())
        self.assertEqual(len(rows), 9)

    def test_staff_can_deactivate_and_reactivate_an_internal_organization(self):
        self.client.force_authenticate(self.staff)
        url = f"{ORGANIZATIONS_URL}{self.internal.id}/verify/"

        response = self.client.post(url, {"action": "suspend"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.internal.refresh_from_db()
        self.assertFalse(self.internal.is_active)
        # Status stays APPROVED — only the active flag changes.
        self.assertEqual(
            self.internal.verification_status,
            Organization.VerificationStatus.APPROVED,
        )

        response = self.client.post(url, {"action": "reactivate"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.internal.refresh_from_db()
        self.assertTrue(self.internal.is_active)


class RetiredAffiliationTests(TestCase):
    """NORSU Student and NORSU Office/Department are retired affiliations.

    Internal organizations are represented by an authorized faculty/staff
    member, so only NORSU Faculty/Staff and External Organization may newly
    be chosen. Existing records keep their stored value and label, but neither
    the registration nor the affiliation endpoint accepts the retired values —
    including through a manually crafted request.
    """

    RETIRED = ("NORSU_STUDENT", "NORSU_OFFICE")

    def setUp(self):
        self.client = APIClient()

    def test_only_two_affiliations_are_selectable(self):
        values = {value for value, _ in User.selectable_affiliation_choices()}
        self.assertEqual(
            values, {User.Affiliation.NORSU_FACULTY_STAFF, User.Affiliation.EXTERNAL_ORGANIZATION}
        )

    def test_affiliation_endpoint_rejects_retired_affiliations(self):
        for index, affiliation in enumerate(self.RETIRED):
            user = User.objects.create_user(
                username=f"campus_{index}",
                password="pass12345",
                role=User.Role.REQUESTER,
            )
            self.client.force_authenticate(user)
            response = self.client.post(
                AFFILIATION_URL, {"affiliation": affiliation}, format="json"
            )
            self.assertEqual(response.status_code, 400, (affiliation, response.content))
            user.refresh_from_db()
            self.assertEqual(user.affiliation, "")

    def test_registration_rejects_retired_affiliations(self):
        for affiliation in self.RETIRED:
            response = self.client.post(
                REGISTER_URL,
                {
                    "username": "crafted",
                    "password": "pass12345",
                    "first_name": "Eve",
                    "last_name": "Spoof",
                    "email": "eve@norsu.edu.ph",
                    "affiliation": affiliation,
                },
                format="json",
            )
            self.assertEqual(response.status_code, 400, (affiliation, response.content))
            self.assertFalse(User.objects.filter(username="crafted").exists())

    def test_legacy_retired_records_are_preserved(self):
        for affiliation in self.RETIRED:
            legacy = User.objects.create_user(
                username=f"legacy_{affiliation.lower()}",
                password="pass12345",
                role=User.Role.REQUESTER,
            )
            # Simulate a row written before the option was retired.
            User.objects.filter(pk=legacy.pk).update(affiliation=affiliation)
            legacy.refresh_from_db()
            self.assertTrue(legacy.has_affiliation)
            self.assertNotEqual(legacy.get_affiliation_display(), "")
            # Legacy accounts remain fully usable campus requesters.
            self.assertTrue(legacy.can_create_reservations)
            self.assertEqual(legacy.trusted_requester_type, "CAMPUS")

    def test_external_registration_cannot_select_internal_type(self):
        """A crafted organization_type=INTERNAL is rejected outright."""
        response = self.client.post(
            REGISTER_URL,
            _external_registration(organization_type="INTERNAL"),
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(_external_organizations().exists())
        self.assertFalse(
            Organization.objects.filter(
                organization_type=Organization.OrganizationType.INTERNAL,
                organization_code__startswith="EXT-",
            ).exists()
        )
