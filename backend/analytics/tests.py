from datetime import date, time

from django.contrib.auth import get_user_model
from django.test import TestCase
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