from datetime import date, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from equipment.models import Equipment, EquipmentCategory
from facilities.models import Facility
from reservations.models import Reservation

User = get_user_model()


class AnalyticsApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="admin", password="pass12345", role=User.Role.ADMIN
        )
        self.client.force_authenticate(self.user)
        facility = Facility.objects.create(
            name="Gym", facility_type=Facility.FacilityType.GYMNASIUM
        )
        category = EquipmentCategory.objects.create(name="Chairs")
        Equipment.objects.create(name="Chair", category=category, total_quantity=10)
        Reservation.objects.create(
            requester=self.user,
            event_name="Event A",
            facility=facility,
            date=date.today(),
            start_time=time(9, 0),
            end_time=time(11, 0),
            status=Reservation.Status.APPROVED,
        )

    def test_summary(self):
        response = self.client.get("/api/analytics/summary/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total_reservations"], 1)

    def test_trends_and_utilization(self):
        self.assertEqual(self.client.get("/api/analytics/trends/").status_code, 200)
        response = self.client.get("/api/analytics/utilization/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("facility", response.json())

    def test_insights(self):
        response = self.client.get("/api/analytics/insights/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("cancellation_rate", response.json())

    def test_reports_list_and_preview(self):
        response = self.client.get("/api/reports/")
        self.assertEqual(response.status_code, 200)
        slugs = [r["slug"] for r in response.json()]
        self.assertIn("reservations", slugs)

        response = self.client.get("/api/reports/reservations/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["preview"]["count"], 1)

    def test_csv_export(self):
        response = self.client.get("/api/reports/reservations/export/csv/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn("Reservation ID", response.content.decode())

    def test_xlsx_export(self):
        response = self.client.get("/api/reports/reservations/export/xlsx/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "spreadsheetml", response["Content-Type"]
        )


class DashboardSummaryScopingTests(TestCase):
    """The summary endpoint is role-scoped server-side.

    Staff see organization-wide counts; requesters see only their own
    activity. The backend decides — the frontend sends no scope hint.
    """

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="admin2", password="pass12345", role=User.Role.ADMIN
        )
        self.requester = User.objects.create_user(
            username="requester2", password="pass12345", role=User.Role.REQUESTER
        )
        self.other = User.objects.create_user(
            username="other2", password="pass12345", role=User.Role.REQUESTER
        )
        self.facility = Facility.objects.create(
            name="Hall", facility_type=Facility.FacilityType.MULTI_PURPOSE, is_active=True
        )
        self.category = EquipmentCategory.objects.create(name="Tables")
        Equipment.objects.create(
            name="Folding Table", category=self.category, total_quantity=40
        )

    def _create(self, requester, status, event_name="Event"):
        return Reservation.objects.create(
            requester=requester,
            event_name=event_name,
            facility=self.facility,
            date=timezone.localdate() + timedelta(days=7),
            start_time=time(9, 0),
            end_time=time(11, 0),
            status=status,
        )

    def test_admin_sees_organization_wide_counts(self):
        self._create(self.requester, Reservation.Status.PENDING)
        self._create(self.other, Reservation.Status.APPROVED)

        self.client.force_authenticate(self.admin)
        data = self.client.get("/api/analytics/summary/").json()

        self.assertEqual(data["total_reservations"], 2)
        self.assertEqual(data["pending_requests"], 1)
        self.assertEqual(data["facilities"], 1)
        self.assertEqual(data["equipment"], 40)  # quantity model

    def test_requester_sees_only_own_counts(self):
        mine = self._create(self.requester, Reservation.Status.PENDING, "Mine")
        self._create(self.other, Reservation.Status.PENDING, "Theirs")
        self._create(self.other, Reservation.Status.APPROVED, "Theirs 2")

        self.client.force_authenticate(self.requester)
        data = self.client.get("/api/analytics/summary/").json()

        self.assertEqual(data["total_reservations"], 1)
        self.assertEqual(data["pending_requests"], 1)
        self.assertEqual([r["id"] for r in data["pending"]], [mine.id])
        self.assertEqual(data["recent"][0]["event_name"], "Mine")

    def test_requester_list_rows_come_from_their_scope(self):
        self._create(self.requester, Reservation.Status.APPROVED, "Mine future")
        self._create(self.other, Reservation.Status.APPROVED, "Other future")

        self.client.force_authenticate(self.requester)
        data = self.client.get("/api/analytics/summary/").json()

        self.assertEqual([r["event_name"] for r in data["upcoming"]], ["Mine future"])

    def test_summary_structure_and_no_sensitive_fields(self):
        self._create(self.requester, Reservation.Status.PENDING)

        self.client.force_authenticate(self.requester)
        data = self.client.get("/api/analytics/summary/").json()

        for key in (
            "total_reservations",
            "pending_requests",
            "active_today",
            "facilities",
            "equipment",
            "today_date",
            "today",
            "upcoming",
            "pending",
            "recent",
            "equipment_attention",
        ):
            self.assertIn(key, data)

        row = data["pending"][0]
        for key in (
            "id",
            "reservation_id",
            "event_name",
            "facility",
            "requester",
            "date",
            "start_time",
            "end_time",
            "status",
            "status_label",
        ):
            self.assertIn(key, row)
        # Privacy: compact rows never carry contact/internal fields.
        for forbidden in (
            "contact_email",
            "contact_number",
            "notes",
            "checkin_code",
            "special_requirements",
        ):
            self.assertNotIn(forbidden, row)


class DashboardTodayTimezoneTests(TestCase):
    """"Today" is the backend's Asia/Manila localdate, not the OS/UTC date."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="tzadmin", password="pass12345", role=User.Role.ADMIN
        )
        self.facility = Facility.objects.create(
            name="TzHall", facility_type=Facility.FacilityType.OTHER, is_active=True
        )

    def test_today_matches_backend_localdate(self):
        today = timezone.localdate()
        Reservation.objects.create(
            requester=self.admin,
            event_name="Today event",
            facility=self.facility,
            date=today,
            start_time=time(9, 0),
            end_time=time(10, 0),
            status=Reservation.Status.APPROVED,
        )
        tomorrow = today + timedelta(days=1)
        Reservation.objects.create(
            requester=self.admin,
            event_name="Tomorrow event",
            facility=self.facility,
            date=tomorrow,
            start_time=time(9, 0),
            end_time=time(10, 0),
            status=Reservation.Status.APPROVED,
        )

        self.client.force_authenticate(self.admin)
        data = self.client.get("/api/analytics/summary/").json()

        self.assertEqual(data["today_date"], today.isoformat())
        self.assertEqual(
            [r["event_name"] for r in data["today"]], ["Today event"]
        )
        self.assertEqual(
            [r["event_name"] for r in data["upcoming"]], ["Tomorrow event"]
        )


class DashboardEmptyDatabaseTests(TestCase):
    """An empty database must report honest zeros, not mock values."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="emptyadmin", password="pass12345", role=User.Role.ADMIN
        )
        self.client.force_authenticate(self.admin)

    def test_empty_database_returns_zeros(self):
        data = self.client.get("/api/analytics/summary/").json()

        self.assertEqual(data["total_reservations"], 0)
        self.assertEqual(data["pending_requests"], 0)
        self.assertEqual(data["active_today"], 0)
        self.assertEqual(data["facilities"], 0)
        self.assertEqual(data["equipment"], 0)
        self.assertEqual(data["today"], [])
        self.assertEqual(data["upcoming"], [])
        self.assertEqual(data["pending"], [])
        self.assertEqual(data["recent"], [])
        self.assertEqual(data["equipment_attention"], [])

    def test_summary_requires_authentication(self):
        self.client.force_authenticate(None)
        response = self.client.get("/api/analytics/summary/")
        self.assertEqual(response.status_code, 401)