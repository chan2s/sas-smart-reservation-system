"""Phase 1: Organization Registry — comprehensive tests for all requirements.

Tests verify:
1. Organization model completeness (all required fields)
2. Automatic creation on successful external reservations
3. Duplicate prevention via normalization
4. Reservation organization_ref linking
5. last_reservation_date tracking
6. Submission IP capture
7. Historical reservation preservation
8. Successful vs failed/abandoned submission handling
"""

from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Organization
from accounts.organization_registry import (
    normalize_organization_name,
    find_organization,
    resolve_organization,
)
from facilities.models import Facility, OperatingHour
from .models import Reservation

User = get_user_model()

RESERVATIONS_URL = "/api/reservations/"
AVAILABILITY_URL = "/api/availability/check/"


class OrganizationModelCompletenessTests(TestCase):
    """Verify Organization model has all required fields from Phase 1."""

    def test_organization_has_all_required_fields(self):
        """Organization model includes all fields specified in requirements."""
        required_fields = {
            'organization_name': 'CharField',
            'organization_type': 'CharField (choices)',
            'contact_person': 'CharField',
            'contact_email': 'EmailField',
            'contact_number': 'CharField',
            'address': 'CharField',
            'normalized_name': 'CharField (auto-computed)',
            'organization_code': 'CharField (auto-generated)',
            'last_reservation_date': 'DateField',
            'is_active': 'BooleanField',
            'created_at': 'DateTimeField (auto_now_add)',
            'updated_at': 'DateTimeField (auto_now)',
            'verification_status': 'CharField (choices)',
        }
        org = Organization.objects.create(
            organization_name="Test Org",
            organization_type=Organization.OrganizationType.NGO,
            contact_person="John Doe",
            contact_email="john@example.com",
        )
        for field_name in required_fields:
            self.assertTrue(hasattr(org, field_name), f"Missing field: {field_name}")
        self.assertIsNotNone(org.organization_code)
        self.assertTrue(org.organization_code.startswith("EXT-"))
        self.assertTrue(org.is_active)
        self.assertEqual(org.verification_status, Organization.VerificationStatus.PENDING)

    def test_organization_supports_internal_and_external_types(self):
        """Organization type can be Internal or External variants."""
        internal = Organization.objects.create(
            organization_name="CAS",
            organization_type=Organization.OrganizationType.INTERNAL,
            contact_person="Faculty",
            contact_email="cas@norsu.edu.ph",
            is_active=True,
        )
        self.assertTrue(internal.is_internal)
        
        external = Organization.objects.create(
            organization_name="NGO Foundation",
            organization_type=Organization.OrganizationType.NGO,
            contact_person="Director",
            contact_email="director@ngo.org",
        )
        self.assertTrue(external.is_external)

    def test_organization_normalized_name_auto_maintained(self):
        """normalized_name is computed from organization_name and kept in sync."""
        org = Organization.objects.create(
            organization_name="ABC  School, Inc.",
            organization_type=Organization.OrganizationType.SCHOOL_UNIVERSITY,
            contact_person="Principal",
            contact_email="principal@school.edu",
        )
        # Name should be normalized: spaces collapsed, trailing "Inc" removed, lowercased
        expected = normalize_organization_name("ABC  School, Inc.")
        self.assertEqual(org.normalized_name, expected)

    def test_organization_code_is_unique_and_sequential(self):
        """organization_code is auto-generated, unique, and sequential."""
        org1 = Organization.objects.create(
            organization_name="First",
            organization_type=Organization.OrganizationType.OTHER,
            contact_person="A",
            contact_email="a@example.com",
        )
        org2 = Organization.objects.create(
            organization_name="Second",
            organization_type=Organization.OrganizationType.OTHER,
            contact_person="B",
            contact_email="b@example.com",
        )
        self.assertEqual(org1.organization_code, "EXT-0001")
        self.assertEqual(org2.organization_code, "EXT-0002")
        self.assertNotEqual(org1.organization_code, org2.organization_code)


class DuplicatePreventionTests(TestCase):
    """Verify duplicate organizations are prevented via normalization."""

    def test_normalized_name_deduplication(self):
        """Same organization under different spellings → one registry record."""
        org1 = Organization.objects.create(
            organization_name="ABC Foundation",
            organization_type=Organization.OrganizationType.NGO,
            contact_person="Director",
            contact_email="abc@example.com",
        )
        # Attempt to create with different casing/spacing
        org2, created = resolve_organization(
            name="abc  foundation",
            organization_type=Organization.OrganizationType.NGO,
            create=True,
            contact_person="Someone Else",
            contact_email="different@example.com",
        )
        self.assertFalse(created)
        self.assertEqual(org2.id, org1.id)
        # Original contact details preserved
        self.assertEqual(org2.contact_person, "Director")
        self.assertEqual(org2.contact_email, "abc@example.com")

    def test_legal_suffix_stripping_in_normalization(self):
        """Trailing legal suffixes (Inc, Ltd, Corp, LLC, etc.) removed in normalization."""
        suffixes = ["Inc", "Inc.", "Incorporated", "Corp", "Corporation", "Co", "Company", "Ltd", "Limited", "LLC"]
        organizations = []
        for i, suffix in enumerate(suffixes):
            org = Organization.objects.create(
                organization_name=f"ABC {suffix}",
                organization_type=Organization.OrganizationType.PRIVATE_ORGANIZATION,
                contact_person=f"Contact {i}",
                contact_email=f"contact{i}@example.com",
            )
            organizations.append(org)
        # All should normalize to "abc" (first token retained minimum)
        normalized_values = set(o.normalized_name for o in organizations)
        self.assertEqual(len(normalized_values), 1)  # All the same
        self.assertIn("abc", list(normalized_values)[0].lower())

    def test_same_name_different_type_are_separate(self):
        """Same normalized name + different type → separate records (allowed, surfaced for review)."""
        school = Organization.objects.create(
            organization_name="ABC Organization",
            organization_type=Organization.OrganizationType.SCHOOL_UNIVERSITY,
            contact_person="Headmaster",
            contact_email="school@example.com",
        )
        ngo = Organization.objects.create(
            organization_name="ABC Organization",
            organization_type=Organization.OrganizationType.NGO,
            contact_person="Director",
            contact_email="ngo@example.com",
        )
        self.assertNotEqual(school.id, ngo.id)
        self.assertEqual(school.normalized_name, ngo.normalized_name)
        self.assertNotEqual(school.organization_type, ngo.organization_type)


class AutomaticOrganizationCreationTests(TestCase):
    """Verify organizations are auto-created on successful external reservation submissions."""

    def setUp(self):
        self.client = APIClient()
        self.staff = User.objects.create_user(
            username="staff",
            password="pass12345",
            role=User.Role.STAFF,
        )
        self.facility = Facility.objects.create(
            name="Hall",
            facility_type=Facility.FacilityType.AVR,
            capacity=100,
        )
        OperatingHour.objects.create(
            facility=self.facility,
            day_of_week=0,
            open_time=time(8, 0),
            close_time=time(20, 0),
        )
        self.day = timezone.localdate() + timedelta(days=1)
        while self.day.weekday() != 0:
            self.day += timedelta(days=1)

    def test_first_external_submission_creates_pending_organization(self):
        """First-time external submission automatically creates org in PENDING status."""
        self.client.force_authenticate(self.staff)
        self.assertEqual(Organization.objects.exclude(organization_type="INTERNAL").count(), 0)
        
        response = self.client.post(
            RESERVATIONS_URL,
            {
                "facility_id": self.facility.id,
                "date": self.day.isoformat(),
                "start_time": "09:00",
                "end_time": "11:00",
                "event_name": "Community Event",
                "event_type": "OTHER",
                "requester_type": "EXTERNAL",
                "organization": "New Foundation",
                "organization_type": "NGO",
                "contact_person": "Manager",
                "contact_email": "manager@example.com",
                "contact_phone": "09171234567",
                "organization_address": "123 Street",
                "expected_participants": 50,
                "items": [],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        
        # Organization should be created
        org = Organization.objects.get(organization_name="New Foundation")
        self.assertEqual(org.organization_type, Organization.OrganizationType.NGO)
        self.assertEqual(org.verification_status, Organization.VerificationStatus.PENDING)
        self.assertEqual(org.contact_person, "Manager")
        self.assertEqual(org.contact_email, "manager@example.com")
        self.assertTrue(org.is_active)
        
        # Reservation should be linked
        reservation = Reservation.objects.get(pk=response.json()["id"])
        self.assertEqual(reservation.organization_ref, org)

    def test_duplicate_submission_reuses_existing_organization(self):
        """Second submission with same org name/type → reuses existing record."""
        org = Organization.objects.create(
            organization_name="XYZ NGO",
            organization_type=Organization.OrganizationType.NGO,
            contact_person="First Contact",
            contact_email="first@example.com",
        )
        initial_count = Organization.objects.exclude(organization_type="INTERNAL").count()
        
        self.client.force_authenticate(self.staff)
        response = self.client.post(
            RESERVATIONS_URL,
            {
                "facility_id": self.facility.id,
                "date": self.day.isoformat(),
                "start_time": "09:00",
                "end_time": "11:00",
                "event_name": "Another Event",
                "event_type": "OTHER",
                "requester_type": "EXTERNAL",
                "organization": "XYZ NGO",
                "organization_type": "NGO",
                "contact_person": "Second Contact",
                "contact_email": "second@example.com",
                "organization_address": "Different Address",
                "expected_participants": 30,
                "items": [],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        
        # No new organization created
        self.assertEqual(
            Organization.objects.exclude(organization_type="INTERNAL").count(),
            initial_count,
        )
        
        # Reservation linked to existing org
        reservation = Reservation.objects.get(pk=response.json()["id"])
        self.assertEqual(reservation.organization_ref, org)

    def test_failed_submission_does_not_create_organization(self):
        """Availability conflict or validation error → no organization created."""
        initial_count = Organization.objects.exclude(organization_type="INTERNAL").count()
        
        self.client.force_authenticate(self.staff)
        response = self.client.post(
            RESERVATIONS_URL,
            {
                "facility_id": self.facility.id,
                "date": self.day.isoformat(),
                "start_time": "25:00",  # Invalid time
                "end_time": "26:00",
                "event_name": "Bad Event",
                "event_type": "OTHER",
                "requester_type": "EXTERNAL",
                "organization": "Should Not Exist",
                "organization_type": "NGO",
                "contact_person": "Contact",
                "contact_email": "invalid.email",  # Invalid email
                "expected_participants": 50,
                "items": [],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        
        # No organization created
        self.assertEqual(
            Organization.objects.exclude(organization_type="INTERNAL").count(),
            initial_count,
        )


class ReservationOrganizationLinkingTests(TestCase):
    """Verify reservations are linked to their organizations."""

    def setUp(self):
        self.client = APIClient()
        self.staff = User.objects.create_user(
            username="staff",
            password="pass12345",
            role=User.Role.STAFF,
        )
        self.facility = Facility.objects.create(
            name="Room",
            facility_type=Facility.FacilityType.CLASSROOM,
            capacity=50,
        )
        OperatingHour.objects.create(
            facility=self.facility,
            day_of_week=2,
            open_time=time(8, 0),
            close_time=time(18, 0),
        )
        self.day = timezone.localdate() + timedelta(days=1)
        while self.day.weekday() != 2:
            self.day += timedelta(days=1)

    def test_reservation_organization_ref_is_populated(self):
        """Successful reservation sets organization_ref to the linked organization."""
        self.client.force_authenticate(self.staff)
        response = self.client.post(
            RESERVATIONS_URL,
            {
                "facility_id": self.facility.id,
                "date": self.day.isoformat(),
                "start_time": "10:00",
                "end_time": "12:00",
                "event_name": "Linked Event",
                "event_type": "ACADEMIC",
                "requester_type": "EXTERNAL",
                "organization": "Test Organization",
                "organization_type": "SCHOOL",
                "contact_person": "Principal",
                "contact_email": "principal@school.edu",
                "expected_participants": 40,
                "items": [],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        
        reservation = Reservation.objects.get(pk=response.json()["id"])
        self.assertIsNotNone(reservation.organization_ref)
        self.assertEqual(
            reservation.organization_ref.organization_name,
            "Test Organization",
        )

    def test_reservation_organization_ref_is_in_response(self):
        """organization_code is exposed in the reservation API response."""
        org = Organization.objects.create(
            organization_name="Known Org",
            organization_type=Organization.OrganizationType.GOVERNMENT_AGENCY,
            contact_person="Administrator",
            contact_email="admin@gov.org",
        )
        self.client.force_authenticate(self.staff)
        response = self.client.post(
            RESERVATIONS_URL,
            {
                "facility_id": self.facility.id,
                "date": self.day.isoformat(),
                "start_time": "14:00",
                "end_time": "16:00",
                "event_name": "Org Event",
                "event_type": "OTHER",
                "requester_type": "EXTERNAL",
                "organization": "Known Org",
                "organization_type": "GOVERNMENT",
                "contact_person": "Someone",
                "contact_email": "someone@example.com",
                "expected_participants": 20,
                "items": [],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["organization_code"], org.organization_code)


class LastReservationDateTrackingTests(TestCase):
    """Verify last_reservation_date is maintained correctly."""

    def setUp(self):
        self.client = APIClient()
        self.staff = User.objects.create_user(
            username="staff",
            password="pass12345",
            role=User.Role.STAFF,
        )
        self.facility = Facility.objects.create(
            name="Gym",
            facility_type=Facility.FacilityType.GYMNASIUM,
            capacity=200,
        )

    def test_last_reservation_date_updated_on_success(self):
        """last_reservation_date is set after first successful submission."""
        org = Organization.objects.create(
            organization_name="Sports Club",
            organization_type=Organization.OrganizationType.SPORTS,
            contact_person="President",
            contact_email="president@sports.org",
        )
        self.assertIsNone(org.last_reservation_date)
        
        for day_offset in range(1, 4):
            day = timezone.localdate() + timedelta(days=day_offset)
            OperatingHour.objects.create(
                facility=self.facility,
                day_of_week=day.weekday(),
                open_time=time(8, 0),
                close_time=time(20, 0),
            )
            
            self.client.force_authenticate(self.staff)
            response = self.client.post(
                RESERVATIONS_URL,
                {
                    "facility_id": self.facility.id,
                    "date": day.isoformat(),
                    "start_time": "10:00",
                    "end_time": "12:00",
                    "event_name": f"Event {day_offset}",
                    "event_type": "SPORTS",
                    "requester_type": "EXTERNAL",
                    "organization": "Sports Club",
                    "organization_type": "SPORTS",
                    "contact_person": "President",
                    "contact_email": "president@sports.org",
                    "expected_participants": 100,
                    "items": [],
                },
                format="json",
            )
            self.assertEqual(response.status_code, 201, response.content)
            
            org.refresh_from_db()
            self.assertEqual(org.last_reservation_date, day)

    def test_last_reservation_date_only_moves_forward(self):
        """last_reservation_date never goes backward (import of old history)."""
        org = Organization.objects.create(
            organization_name="Historical Org",
            organization_type=Organization.OrganizationType.COMMUNITY_ORGANIZATION,
            contact_person="Leader",
            contact_email="leader@community.org",
        )
        
        # Manually set to a future date
        future = timezone.localdate() + timedelta(days=100)
        org.last_reservation_date = future
        org.save(update_fields=["last_reservation_date"])
        
        # Mock record an earlier reservation
        from accounts.organization_registry import record_organization_reservation
        older_day = timezone.localdate() - timedelta(days=10)
        older_res = Reservation(
            organization_ref=org,
            date=older_day,
            contact_person="Someone",
            contact_email="someone@example.com",
            contact_phone="09171234567",
        )
        record_organization_reservation(org, older_res, update_contact=False)
        
        org.refresh_from_db()
        # Date should not move backward
        self.assertEqual(org.last_reservation_date, future)


class SubmissionIPCaptureTests(TestCase):
    """Verify submission_ip is captured on successful reservation submission."""

    def setUp(self):
        self.client = APIClient()
        self.staff = User.objects.create_user(
            username="staff",
            password="pass12345",
            role=User.Role.STAFF,
        )
        self.facility = Facility.objects.create(
            name="Conference Room",
            facility_type=Facility.FacilityType.CONFERENCE_ROOM,
            capacity=30,
        )
        OperatingHour.objects.create(
            facility=self.facility,
            day_of_week=1,
            open_time=time(9, 0),
            close_time=time(17, 0),
        )
        self.day = timezone.localdate() + timedelta(days=1)
        while self.day.weekday() != 1:
            self.day += timedelta(days=1)

    def test_submission_ip_is_captured_on_success(self):
        """submission_ip is recorded after successful reservation save."""
        self.client.force_authenticate(self.staff)
        # Client automatically provides REMOTE_ADDR
        response = self.client.post(
            RESERVATIONS_URL,
            {
                "facility_id": self.facility.id,
                "date": self.day.isoformat(),
                "start_time": "10:00",
                "end_time": "11:00",
                "event_name": "IP Test Event",
                "event_type": "MEETING",
                "requester_type": "EXTERNAL",
                "organization": "IP Test Org",
                "organization_type": "OTHER",
                "contact_person": "Contact",
                "contact_email": "contact@example.com",
                "expected_participants": 20,
                "items": [],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        
        reservation = Reservation.objects.get(pk=response.json()["id"])
        # IP should be captured (test client provides 127.0.0.1 by default)
        self.assertIsNotNone(reservation.submission_ip)

    def test_submission_ip_is_not_exposed_in_public_api(self):
        """submission_ip is staff-only; never in public reservation API."""
        self.client.force_authenticate(self.staff)
        response = self.client.post(
            RESERVATIONS_URL,
            {
                "facility_id": self.facility.id,
                "date": self.day.isoformat(),
                "start_time": "11:00",
                "end_time": "12:00",
                "event_name": "Privacy Test",
                "event_type": "OTHER",
                "requester_type": "EXTERNAL",
                "organization": "Privacy Org",
                "organization_type": "OTHER",
                "contact_person": "Contact",
                "contact_email": "contact@example.com",
                "expected_participants": 15,
                "items": [],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        
        body = response.json()
        # submission_ip should NOT be in the response
        self.assertNotIn("submission_ip", body)
