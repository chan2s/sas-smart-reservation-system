"""Tests for administrator facility management.

Covers the end-to-end admin flow:

* only SAS staff may create / edit / disable / archive / delete facilities;
* new facilities appear in the API (and therefore in the reservation form);
* disabling a facility hides it from requesters and blocks new reservations;
* re-enabling it makes it reservable again;
* disabling is NOT deletion — historical reservations stay intact;
* a facility with reservation history is archived (never hard-deleted), so the
  PROTECT foreign key can never be broken;
* duplicate names are rejected with a clear message.
"""

import json
from datetime import date, time

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from reservations.models import Reservation
from reservations.services.availability import check_availability

from .models import Facility, OperatingHour

User = get_user_model()

#: A weekday with operating hours configured (Tuesday).
EVENT_DATE = date(2026, 12, 1)


class AdminFacilityManagementTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="admin", password="pass12345", role=User.Role.ADMIN
        )
        self.staff = User.objects.create_user(
            username="staff", password="pass12345", role=User.Role.STAFF
        )
        self.requester = User.objects.create_user(
            username="requester", password="pass12345", role=User.Role.REQUESTER
        )

    def _auth(self, user=None):
        self.client.force_authenticate(user or self.admin)

    def _facility(self, name="Gymnasium", **kwargs):
        facility = Facility.objects.create(
            name=name,
            facility_type=Facility.FacilityType.GYMNASIUM,
            capacity=500,
            **kwargs,
        )
        OperatingHour.objects.create(
            facility=facility,
            day_of_week=EVENT_DATE.weekday(),
            open_time=time(8, 0),
            close_time=time(17, 0),
        )
        return facility

    # -- permissions ------------------------------------------------------

    def test_requester_cannot_create_facility(self):
        self._auth(self.requester)
        response = self.client.post(
            "/api/facilities/", {"name": "New Hall"}, format="json"
        )
        self.assertEqual(response.status_code, 403, response.content)

    def test_unauthenticated_cannot_list_facilities(self):
        response = self.client.get("/api/facilities/")
        self.assertIn(response.status_code, (401, 403))

    # -- create / read ----------------------------------------------------

    def test_admin_creates_facility_and_it_appears_in_the_list(self):
        self._auth()
        response = self.client.post(
            "/api/facilities/",
            {
                "name": "New Auditorium",
                "facility_type": "MULTI_PURPOSE",
                "capacity": 300,
                "location": "Main Building",
                "status": "OPERATIONAL",
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["name"], "New Auditorium")
        self.assertTrue(body["is_active"])
        self.assertFalse(body["has_history"])

        listed = self.client.get("/api/facilities/").json()
        self.assertIn("New Auditorium", {row["name"] for row in listed})

    def test_duplicate_facility_name_is_rejected(self):
        self._auth()
        self._facility(name="Gymnasium")
        response = self.client.post(
            "/api/facilities/", {"name": "Gymnasium"}, format="json"
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("name", response.json())

    def test_staff_can_create_facility(self):
        self._auth(self.staff)
        response = self.client.post(
            "/api/facilities/", {"name": "Staff Hall"}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.content)

    # -- multipart form (the admin UI's actual payload) --------------------

    def test_create_facility_via_multipart_form(self):
        self._auth()
        response = self.client.post(
            "/api/facilities/",
            {
                "name": "Form Hall",
                "facility_type": "MULTI_PURPOSE",
                "description": "A hall",
                "capacity": "150",
                "location": "Building A",
                "status": "OPERATIONAL",
                "is_active": "true",
                "rules": json.dumps(["Clean up after use"]),
                "built_ins": json.dumps(["tables", "chairs"]),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["built_ins"], ["tables", "chairs"])
        self.assertEqual(body["rules"], ["Clean up after use"])
        self.assertEqual(body["capacity"], 150)

    def test_built_ins_can_be_cleared_via_multipart(self):
        facility = self._facility(built_ins=["tables"])
        self._auth()
        response = self.client.patch(
            f"/api/facilities/{facility.id}/",
            {"built_ins": "[]"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["built_ins"], [])

    # -- edit -------------------------------------------------------------

    def test_admin_edits_facility_and_change_is_reflected(self):
        facility = self._facility()
        self._auth()
        response = self.client.patch(
            f"/api/facilities/{facility.id}/",
            {"location": "New Location", "capacity": 900},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["location"], "New Location")
        self.assertEqual(body["capacity"], 900)
        facility.refresh_from_db()
        self.assertEqual(facility.location, "New Location")

    # -- enable / disable -------------------------------------------------

    def test_disabled_facility_is_hidden_from_requesters(self):
        facility = self._facility()
        self._auth()
        disable = self.client.patch(
            f"/api/facilities/{facility.id}/", {"is_active": False}, format="json"
        )
        self.assertEqual(disable.status_code, 200, disable.content)

        self._auth(self.requester)
        listed = self.client.get("/api/facilities/").json()
        self.assertNotIn(facility.id, {row["id"] for row in listed})

    def test_staff_can_include_archived_facilities(self):
        facility = self._facility(is_active=False)
        self._auth()
        default = self.client.get("/api/facilities/").json()
        self.assertNotIn(facility.id, {row["id"] for row in default})
        archived = self.client.get("/api/facilities/?include_inactive=true").json()
        self.assertIn(facility.id, {row["id"] for row in archived})

    def test_disabled_facility_cannot_be_reserved_and_re_enabled_can(self):
        facility = self._facility()
        self._auth()

        # Active: a clean window is available.
        ok = check_availability(facility.id, EVENT_DATE, time(9, 0), time(10, 0))
        self.assertTrue(ok["overall"]["ok"], ok["problems"])

        self.client.patch(
            f"/api/facilities/{facility.id}/", {"is_active": False}, format="json"
        )
        blocked = check_availability(facility.id, EVENT_DATE, time(9, 0), time(10, 0))
        self.assertFalse(blocked["overall"]["ok"])
        self.assertTrue(
            any(problem["type"] == "facility" for problem in blocked["problems"])
        )

        self.client.patch(
            f"/api/facilities/{facility.id}/", {"is_active": True}, format="json"
        )
        again = check_availability(facility.id, EVENT_DATE, time(9, 0), time(10, 0))
        self.assertTrue(again["overall"]["ok"], again["problems"])

    # -- delete / archive -------------------------------------------------

    def _reserve(self, facility):
        return Reservation.objects.create(
            facility=facility,
            date=EVENT_DATE,
            start_time=time(9, 0),
            end_time=time(10, 0),
            event_name="Reserved event",
        )

    def test_delete_with_history_archives_instead_of_deleting(self):
        facility = self._facility()
        reservation = self._reserve(facility)

        self._auth()
        response = self.client.delete(f"/api/facilities/{facility.id}/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["archived"])

        facility.refresh_from_db()
        self.assertFalse(facility.is_active)
        # The historical reservation is untouched.
        self.assertTrue(Reservation.objects.filter(pk=reservation.pk).exists())

    def test_delete_without_history_removes_the_facility(self):
        facility = self._facility()
        self._auth()
        response = self.client.delete(f"/api/facilities/{facility.id}/")
        self.assertEqual(response.status_code, 204, response.content)
        self.assertFalse(Facility.objects.filter(pk=facility.pk).exists())

    def test_requester_cannot_delete_facility(self):
        facility = self._facility()
        self._auth(self.requester)
        response = self.client.delete(f"/api/facilities/{facility.id}/")
        self.assertEqual(response.status_code, 403, response.content)
        self.assertTrue(Facility.objects.filter(pk=facility.pk).exists())
