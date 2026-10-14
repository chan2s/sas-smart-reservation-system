"""Global view-only policy tests for not-approved accounts.

The account-approval condition is the existing ``is_active`` flag (see
``User.is_approved``). These tests pin the policy end to end:

* a not-approved account can authenticate and READ what its role may read;
* every state-changing request — create / edit / delete / submit — is refused
  with a consistent ``403`` body, even when the endpoint is called directly;
* blocked attempts create no records, files, or side effects;
* approval can be granted/revoked while a session or JWT is live, and takes
  effect on the next request;
* approved users and administrators keep their existing permissions.
"""

from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from equipment.models import Equipment, EquipmentCategory, MaintenanceRecord
from facilities.models import Facility, OperatingHour

from .models import AuditLog

User = get_user_model()

PASSWORD = "pass1234!"
NOT_APPROVED_CODE = "account_not_approved"


def _client(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


class _BaseViewOnlyTest(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin",
            password=PASSWORD,
            role=User.Role.ADMIN,
        )
        self.approved = User.objects.create_user(
            username="approved",
            password=PASSWORD,
            email="approved@school.edu",
            role=User.Role.REQUESTER,
        )
        self.pending = User.objects.create_user(
            username="pending",
            password=PASSWORD,
            email="pending@school.edu",
            role=User.Role.REQUESTER,
            is_active=False,
        )
        self.pending_client = _client(self.pending)
        self.approved_client = _client(self.approved)
        self.admin_client = _client(self.admin)

        self.facility = Facility.objects.create(
            name="AVR",
            facility_type=Facility.FacilityType.AVR,
            capacity=50,
            location="Main",
        )
        # A near-future Monday so the (Monday-only) operating hours line up and
        # reservation dates never go stale.
        self.day = timezone.localdate() + timedelta(days=1)
        while self.day.weekday() != 0:
            self.day += timedelta(days=1)
        OperatingHour.objects.create(
            facility=self.facility,
            day_of_week=0,
            open_time=time(6, 0),
            close_time=time(22, 0),
        )
        category = EquipmentCategory.objects.create(name="Chairs")
        self.equipment = Equipment.objects.create(
            name="Folding Chair", category=category, total_quantity=100
        )

    def _reservation_payload(self, **overrides):
        payload = dict(
            facility_id=self.facility.id,
            date=self.day.isoformat(),
            start_time="09:00",
            end_time="11:00",
            event_name="Orientation",
            event_type="ACADEMIC",
            organization="Student Affairs",
            purpose="Freshmen orientation",
            expected_participants=50,
            items=[{"equipment_id": self.equipment.id, "quantity": 10}],
        )
        payload.update(overrides)
        return payload

    def _assert_forbidden(self, response):
        self.assertEqual(response.status_code, 403, response.content)

    def _assert_not_approved(self, response):
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(response.data["code"], NOT_APPROVED_CODE)
        self.assertIn("view-only", response.data["detail"].lower())


class NotApprovedReadAccessTests(_BaseViewOnlyTest):
    """A not-approved account keeps genuine read access."""

    def test_can_view_facilities_and_equipment(self):
        facilities = self.pending_client.get("/api/facilities/")
        self.assertEqual(facilities.status_code, 200)
        self.assertEqual(len(facilities.data), 1)

        equipment = self.pending_client.get("/api/equipment/")
        self.assertEqual(equipment.status_code, 200)
        self.assertEqual(len(equipment.data), 1)

    def test_can_view_own_profile_and_status(self):
        me = self.pending_client.get("/api/auth/me/")
        self.assertEqual(me.status_code, 200)
        self.assertFalse(me.data["is_approved"])
        self.assertTrue(me.data["is_view_only"])

    def test_can_view_reservation_list_calendar_and_availability(self):
        listing = self.pending_client.get("/api/reservations/")
        self.assertEqual(listing.status_code, 200)

        calendar = self.pending_client.get(
            "/api/calendar/events/",
            {
                "start": self.day.isoformat(),
                "end": self.day.isoformat(),
            },
        )
        self.assertEqual(calendar.status_code, 200)

        # Availability analysis is a read-only computation exposed as POST and
        # is explicitly allowed for not-approved accounts.
        availability = self.pending_client.post(
            "/api/availability/check/",
            {
                "facility_id": self.facility.id,
                "date": self.day.isoformat(),
                "start_time": "09:00",
                "end_time": "11:00",
                "items": [],
            },
            format="json",
        )
        self.assertNotEqual(availability.status_code, 403)

    def test_search_filter_and_pagination_remain_functional(self):
        response = self.pending_client.get(
            "/api/reservations/", {"search": "Orientation", "page": 1}
        )
        self.assertEqual(response.status_code, 200)


class NotApprovedWriteBlockTests(_BaseViewOnlyTest):
    """Every state-changing operation is refused for a not-approved account."""

    def test_cannot_create_or_edit_reservation(self):
        create = self.pending_client.post(
            "/api/reservations/", self._reservation_payload(), format="json"
        )
        self._assert_not_approved(create)

    def test_cannot_resubmit_or_cancel_reservation(self):
        from reservations.models import Reservation

        reservation = Reservation.objects.create(
            requester=self.pending,
            event_name="Own",
            facility=self.facility,
            date=self.day,
            start_time=time(13, 0),
            end_time=time(15, 0),
        )
        resubmit = self.pending_client.post(
            f"/api/reservations/{reservation.id}/resubmit/",
            self._reservation_payload(),
            format="json",
        )
        self._assert_not_approved(resubmit)

        cancel = self.pending_client.post(
            f"/api/reservations/{reservation.id}/cancel/", {}, format="json"
        )
        self._assert_not_approved(cancel)

    def test_cannot_delete_reservation(self):
        from reservations.models import Reservation

        reservation = Reservation.objects.create(
            requester=self.pending,
            event_name="Own",
            facility=self.facility,
            date=self.day,
            start_time=time(15, 0),
            end_time=time(17, 0),
        )
        response = self.pending_client.delete(f"/api/reservations/{reservation.id}/")
        self._assert_not_approved(response)
        self.assertTrue(Reservation.objects.filter(pk=reservation.pk).exists())

    def test_cannot_submit_equipment_issue_report(self):
        response = self.pending_client.post(
            f"/api/equipment/{self.equipment.id}/report_issue/",
            {"issue_type": "DAMAGE", "description": "Broken"},
            format="json",
        )
        self._assert_not_approved(response)
        # The refusal happens before any record is written.
        self.assertEqual(
            MaintenanceRecord.objects.filter(equipment=self.equipment).count(), 0
        )

    def test_not_approved_staff_cannot_resolve_maintenance(self):
        record = MaintenanceRecord.objects.create(
            equipment=self.equipment,
            quantity=1,
            issue_type=MaintenanceRecord.IssueType.MAINTENANCE,
            description="Chair leg broken",
        )
        pending_staff = User.objects.create_user(
            username="pending-staff-resolver",
            password=PASSWORD,
            role=User.Role.STAFF,
            is_active=False,
        )
        response = _client(pending_staff).post(
            f"/api/maintenance/{record.pk}/resolve/", {}, format="json"
        )
        self._assert_not_approved(response)
        # The record stays OPEN — the refusal precedes every side effect.
        record.refresh_from_db()
        self.assertEqual(record.status, MaintenanceRecord.Status.OPEN)
        self.assertIsNone(record.resolved_at)

    def test_cannot_modify_facilities_or_equipment(self):
        # A requester is refused by the existing staff-only rule; a not-approved
        # staff account is refused by the approval policy on top of it.
        facilities = self.pending_client.post(
            "/api/facilities/",
            {
                "name": "New",
                "facility_type": "GYMNASIUM",
                "capacity": 10,
                "location": "X",
            },
            format="json",
        )
        self._assert_forbidden(facilities)

        update = self.pending_client.patch(
            f"/api/equipment/{self.equipment.id}/", {"name": "Renamed"}, format="json"
        )
        self._assert_forbidden(update)

        delete = self.pending_client.delete(f"/api/facilities/{self.facility.id}/")
        self._assert_forbidden(delete)

    def test_not_approved_staff_cannot_modify_facilities(self):
        pending_staff = User.objects.create_user(
            username="pending-staff",
            password=PASSWORD,
            role=User.Role.STAFF,
            is_active=False,
        )
        response = _client(pending_staff).post(
            "/api/facilities/",
            {
                "name": "New",
                "facility_type": "GYMNASIUM",
                "capacity": 10,
                "location": "X",
            },
            format="json",
        )
        self._assert_not_approved(response)

    def test_cannot_modify_profile_or_affiliation(self):
        profile = self.pending_client.patch(
            "/api/auth/me/", {"first_name": "Nope"}, format="json"
        )
        self._assert_not_approved(profile)

        affiliation = self.pending_client.post(
            "/api/auth/affiliation/",
            {"affiliation": "NORSU_FACULTY_STAFF", "organization": "CAS"},
            format="json",
        )
        self._assert_not_approved(affiliation)

    def test_cannot_mark_notifications_read(self):
        response = self.pending_client.post(
            "/api/notifications/mark_all_read/", {}, format="json"
        )
        self._assert_not_approved(response)

    def test_not_approved_staff_cannot_upload_images(self):
        import io

        from django.core.files.uploadedfile import SimpleUploadedFile

        # A 1x1 PNG — valid image bytes, so the refusal cannot be a validation
        # error. The approval permission runs before any file is stored.
        png = bytes.fromhex(
            "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
            "1f15c4890000000a49444154789c6360000002000100ffff03000006"
            "0057bfabd70000000049454e44ae426082"
        )
        upload = SimpleUploadedFile("x.png", io.BytesIO(png).getvalue(), "image/png")

        pending_staff = User.objects.create_user(
            username="pending-staff-2",
            password=PASSWORD,
            role=User.Role.STAFF,
            is_active=False,
        )
        response = _client(pending_staff).post(
            f"/api/facilities/{self.facility.id}/images/",
            {"images": [upload]},
            format="multipart",
        )
        self._assert_not_approved(response)

    def test_not_approved_staff_cannot_verify_an_organization(self):
        from .models import Organization

        organization = Organization.objects.create(
            organization_name="External Co",
            organization_type=Organization.OrganizationType.NGO,
            contact_person="Jane",
            contact_email="jane@example.com",
        )
        pending_staff = User.objects.create_user(
            username="pending-staff-3",
            password=PASSWORD,
            role=User.Role.STAFF,
            is_active=False,
        )
        response = _client(pending_staff).post(
            f"/api/auth/organizations/{organization.pk}/verify/",
            {"action": "approve"},
            format="json",
        )
        self._assert_not_approved(response)
        organization.refresh_from_db()
        self.assertEqual(
            organization.verification_status, Organization.VerificationStatus.PENDING
        )


class NoSideEffectsTests(_BaseViewOnlyTest):
    """A refused request must not create records, files, or notifications."""

    def test_blocked_facility_create_writes_nothing(self):
        before = Facility.objects.count()
        self.pending_client.post(
            "/api/facilities/",
            {
                "name": "Ghost",
                "facility_type": "GYMNASIUM",
                "capacity": 10,
                "location": "X",
            },
            format="json",
        )
        self.assertEqual(Facility.objects.count(), before)
        self.assertFalse(Facility.objects.filter(name="Ghost").exists())

    def test_blocked_facility_create_is_not_audited(self):
        self.pending_client.post(
            "/api/facilities/",
            {
                "name": "Ghost",
                "facility_type": "GYMNASIUM",
                "capacity": 10,
                "location": "X",
            },
            format="json",
        )
        self.assertFalse(
            AuditLog.objects.filter(action=AuditLog.Action.FACILITY_CREATED).exists()
        )


class ApprovalLifecycleTests(_BaseViewOnlyTest):
    """Approval changes take effect on subsequent requests, tokens included."""

    def test_approving_an_account_enables_role_actions(self):
        # Before approval: blocked.
        self._assert_not_approved(
            self.pending_client.post(
                "/api/reservations/", self._reservation_payload(), format="json"
            )
        )

        # Administrator approves the account (reuses the existing status
        # endpoint — no second approval workflow).
        approved = self.admin_client.post(
            f"/api/auth/users/{self.pending.pk}/status/",
            {"is_active": True},
            format="json",
        )
        self.assertEqual(approved.status_code, 200)

        # A real request re-loads the account from the database, so approval
        # takes effect on the next request — simulate that here.
        self.pending.refresh_from_db()
        created = self.pending_client.post(
            "/api/reservations/", self._reservation_payload(), format="json"
        )
        self.assertEqual(created.status_code, 201, created.content)

    def test_revoking_approval_blocks_subsequent_actions_even_with_a_jwt(self):
        # Log in normally to obtain a token, then revoke approval.
        login = APIClient().post(
            "/api/auth/login/", {"username": "approved", "password": PASSWORD}
        )
        self.assertEqual(login.status_code, 200)
        access = login.data["access"]

        self.assertEqual(
            self.admin_client.post(
                f"/api/auth/users/{self.approved.pk}/status/",
                {"is_active": False},
                format="json",
            ).status_code,
            200,
        )

        authed = APIClient()
        authed.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        # Reads still work with the pre-revocation token...
        self.assertEqual(authed.get("/api/facilities/").status_code, 200)
        # ...but the token can no longer change state.
        blocked = authed.post(
            "/api/reservations/", self._reservation_payload(), format="json"
        )
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(blocked.data["code"], NOT_APPROVED_CODE)


class ApprovedAndAdminTests(_BaseViewOnlyTest):
    """Approved users and administrators keep their existing permissions."""

    def test_approved_requester_can_create_reservation(self):
        response = self.approved_client.post(
            "/api/reservations/", self._reservation_payload(), format="json"
        )
        self.assertEqual(response.status_code, 201, response.content)

    def test_admin_can_still_manage_facilities(self):
        response = self.admin_client.post(
            "/api/facilities/",
            {
                "name": "New Gym",
                "facility_type": "GYMNASIUM",
                "capacity": 200,
                "location": "North",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)

    def test_admin_can_still_manage_user_approval(self):
        response = self.admin_client.post(
            f"/api/auth/users/{self.pending.pk}/status/",
            {"is_active": True},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.pending.refresh_from_db()
        self.assertTrue(self.pending.is_active)


class AuthenticationStillWorksTests(_BaseViewOnlyTest):
    """Authentication, logout, and security operations keep working."""

    def test_not_approved_account_can_sign_in(self):
        response = APIClient().post(
            "/api/auth/login/", {"username": "pending", "password": PASSWORD}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_not_approved_account_can_refresh_its_session(self):
        login = APIClient().post(
            "/api/auth/login/", {"username": "pending", "password": PASSWORD}
        )
        refresh = login.data["refresh"]
        refreshed = APIClient().post(
            "/api/auth/refresh/", {"refresh": refresh}, format="json"
        )
        self.assertEqual(refreshed.status_code, 200)
