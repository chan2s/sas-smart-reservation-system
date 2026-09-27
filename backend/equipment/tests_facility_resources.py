"""Tests for administrator configuration of facility resources.

Covers the write side of the facility <-> equipment relationship:

* only SAS staff may create/edit/remove assignments;
* a resource can be assigned to more than one facility, never twice to one;
* the reservation form's read endpoint reflects admin changes dynamically;
* a resource marked MAINTENANCE/UNAVAILABLE/DAMAGED stops being reservable;
* the Django admin "Manage Equipment" page adds and removes assignments.
"""

from datetime import date, time

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from facilities.models import Facility, OperatingHour
from reservations.services.availability import check_availability

from .models import Equipment, EquipmentCategory, FacilityResource

User = get_user_model()


class FacilityResourceAdminApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.staff = User.objects.create_user(
            username="staff", password="pass12345", role=User.Role.STAFF
        )
        self.requester = User.objects.create_user(
            username="requester", password="pass12345", role=User.Role.REQUESTER
        )

        self.gym = Facility.objects.create(
            name="Gymnasium", facility_type=Facility.FacilityType.GYMNASIUM, capacity=1000
        )
        self.avr = Facility.objects.create(
            name="Audio-Visual Room", facility_type=Facility.FacilityType.AVR, capacity=120
        )
        self.category = EquipmentCategory.objects.create(name="Audio Equipment")
        self.sound = Equipment.objects.create(
            name="Sound System", category=self.category, total_quantity=2
        )

    def _auth(self, user=None):
        self.client.force_authenticate(user or self.staff)

    # -- permissions ------------------------------------------------------

    def test_requester_cannot_create_assignment(self):
        self._auth(self.requester)
        response = self.client.post(
            "/api/facility-resources/",
            {"facility": self.gym.id, "equipment": self.sound.id},
            format="json",
        )
        self.assertEqual(response.status_code, 403, response.content)

    def test_unauthenticated_cannot_read_assignments(self):
        response = self.client.get("/api/facility-resources/")
        self.assertIn(response.status_code, (401, 403))

    # -- create / read ----------------------------------------------------

    def test_staff_assigns_equipment_to_facility(self):
        self._auth()
        response = self.client.post(
            "/api/facility-resources/",
            {"facility": self.gym.id, "equipment": self.sound.id},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["equipment_id"], self.sound.id)
        self.assertEqual(body["name"], "Sound System")

        # The reservation form's endpoint reflects the new assignment.
        listing = self.client.get(f"/api/facilities/{self.gym.id}/resources/").json()
        self.assertEqual(
            {row["name"] for row in listing["resources"]}, {"Sound System"}
        )

    def test_same_equipment_can_be_assigned_to_multiple_facilities(self):
        self._auth()
        for facility in (self.gym, self.avr):
            response = self.client.post(
                "/api/facility-resources/",
                {"facility": facility.id, "equipment": self.sound.id},
                format="json",
            )
            self.assertEqual(response.status_code, 201, response.content)

    def test_duplicate_assignment_is_rejected(self):
        self._auth()
        FacilityResource.objects.create(facility=self.gym, equipment=self.sound)
        response = self.client.post(
            "/api/facility-resources/",
            {"facility": self.gym.id, "equipment": self.sound.id},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("equipment", response.json())

    def test_list_can_be_filtered_by_facility(self):
        self._auth()
        FacilityResource.objects.create(facility=self.gym, equipment=self.sound)
        projector = Equipment.objects.create(
            name="Projector", category=self.category, total_quantity=1
        )
        FacilityResource.objects.create(facility=self.avr, equipment=projector)

        gym = self.client.get(
            f"/api/facility-resources/?facility={self.gym.id}"
        ).json()
        self.assertEqual([row["name"] for row in gym], ["Sound System"])

    # -- update / configuration ------------------------------------------

    def test_staff_configures_quantity_status_and_fees(self):
        self._auth()
        resource = FacilityResource.objects.create(
            facility=self.gym, equipment=self.sound
        )
        response = self.client.patch(
            f"/api/facility-resources/{resource.id}/",
            {
                "quantity": 1,
                "status": FacilityResource.Status.MAINTENANCE,
                "operator_available": True,
                "operator_fee": "500.00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["quantity"], 1)
        self.assertEqual(body["status"], "MAINTENANCE")
        self.assertTrue(body["operator_available"])

    def test_required_operator_is_also_marked_available(self):
        self._auth()
        resource = FacilityResource.objects.create(
            facility=self.gym, equipment=self.sound
        )
        response = self.client.patch(
            f"/api/facility-resources/{resource.id}/",
            {"operator_required": True, "operator_fee": "500.00"},
            format="json",
        )
        self.assertTrue(response.json()["operator_available"])

    def test_removal_reflects_in_reservation_form(self):
        self._auth()
        resource = FacilityResource.objects.create(
            facility=self.gym, equipment=self.sound
        )
        response = self.client.delete(f"/api/facility-resources/{resource.id}/")
        self.assertEqual(response.status_code, 204, response.content)
        listing = self.client.get(f"/api/facilities/{self.gym.id}/resources/").json()
        self.assertEqual(listing["resources"], [])

    def test_inactive_assignments_hidden_unless_requested(self):
        self._auth()
        resource = FacilityResource.objects.create(
            facility=self.gym, equipment=self.sound, is_active=False
        )
        hidden = self.client.get(
            f"/api/facility-resources/?facility={self.gym.id}"
        ).json()
        self.assertEqual(hidden, [])
        shown = self.client.get(
            f"/api/facility-resources/?facility={self.gym.id}&include_inactive=true"
        ).json()
        self.assertEqual([row["id"] for row in shown], [resource.id])

    # -- status affects reservability (Test 5) ----------------------------

    def test_maintenance_resource_is_not_reservable(self):
        FacilityResource.objects.create(
            facility=self.gym,
            equipment=self.sound,
            status=FacilityResource.Status.MAINTENANCE,
        )
        report = check_availability(
            self.gym.id,
            date(2026, 9, 30),
            time(9, 0),
            time(11, 0),
            [{"equipment_id": self.sound.id, "quantity": 1}],
        )
        item = next(
            row for row in report["items"] if row["equipment_id"] == self.sound.id
        )
        self.assertEqual(item["available"], 0)
        self.assertEqual(item["status"], "UNAVAILABLE")
        self.assertFalse(report["overall"]["ok"])

    def test_damaged_status_is_supported_and_blocks_reservation(self):
        self.assertIn("DAMAGED", FacilityResource.Status.values)
        FacilityResource.objects.create(
            facility=self.gym,
            equipment=self.sound,
            status=FacilityResource.Status.DAMAGED,
        )
        report = check_availability(
            self.gym.id,
            date(2026, 9, 30),
            time(9, 0),
            time(11, 0),
            [{"equipment_id": self.sound.id, "quantity": 1}],
        )
        item = next(
            row for row in report["items"] if row["equipment_id"] == self.sound.id
        )
        self.assertEqual(item["available"], 0)


class ManageEquipmentAdminPageTests(TestCase):
    """The custom Django admin page that assigns resources to a facility."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin", password="pass12345", role=User.Role.ADMIN
        )
        self.client.force_login(self.admin)
        self.facility = Facility.objects.create(
            name="Gymnasium", facility_type=Facility.FacilityType.GYMNASIUM
        )
        OperatingHour.objects.create(
            facility=self.facility,
            day_of_week=0,
            open_time=time(6, 0),
            close_time=time(22, 0),
        )
        self.category = EquipmentCategory.objects.create(name="Audio Equipment")
        self.sound = Equipment.objects.create(
            name="Sound System", category=self.category, total_quantity=2
        )

    def _url(self):
        return reverse(
            "admin:facilities_facility_manage_equipment", args=[self.facility.pk]
        )

    def test_page_loads_for_admin(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sound System")

    def test_post_assigns_and_removes(self):
        response = self.client.post(
            self._url(),
            {"_save": "1", "equipment": [str(self.sound.id)]},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            FacilityResource.objects.filter(
                facility=self.facility, equipment=self.sound
            ).exists()
        )

        # Unticking every item removes the assignment.
        self.client.post(self._url(), {"_save": "1", "equipment": []}, follow=True)
        self.assertFalse(
            FacilityResource.objects.filter(
                facility=self.facility, equipment=self.sound
            ).exists()
        )

    def test_quick_add_and_remove_buttons(self):
        self.client.post(self._url(), {"add": self.sound.id}, follow=True)
        resource = FacilityResource.objects.get(
            facility=self.facility, equipment=self.sound
        )
        self.client.post(self._url(), {"remove": self.sound.id}, follow=True)
        self.assertFalse(FacilityResource.objects.filter(pk=resource.pk).exists())
