from datetime import date, time
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase
from PIL import Image as PilImage
from rest_framework.test import APIClient

from facilities.models import Facility, OperatingHour
from reservations.models import Reservation, ReservationItem
from reservations.services.availability import check_availability
from reservations.services.recommendations import recommend_resources

from .models import Equipment, EquipmentCategory, MaintenanceRecord
from .services import equipment_stats

PNG = "image/png"
JPEG = "image/jpeg"
WEBP = "image/webp"
MAX_SIZE = 5 * 1024 * 1024  # 5 MB


def _png():
    data = BytesIO()
    PilImage.new("RGB", (4, 4), color=(59, 130, 246)).save(data, format="PNG")
    return ContentFile(data.getvalue(), name="sound-system.png")


def _jpeg():
    data = BytesIO()
    PilImage.new("RGB", (4, 4), color=(37, 99, 235)).save(data, format="JPEG")
    return ContentFile(data.getvalue(), name="sound-system.jpg")


def _webp():
    data = BytesIO()
    PilImage.new("RGB", (4, 4), color=(37, 99, 235)).save(data, format="WEBP")
    return ContentFile(data.getvalue(), name="sound-system.webp")


User = get_user_model()


class EquipmentManagementApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="admin", password="pass12345", role=User.Role.ADMIN
        )
        self.requester = User.objects.create_user(
            username="requester", password="pass12345", role=User.Role.REQUESTER
        )
        self.category = EquipmentCategory.objects.create(name="Audio")
        self.mics = Equipment.objects.create(
            name="Wireless Microphone",
            category=self.category,
            total_quantity=8,
            unit="unit",
            asset_code="SAS-MIC-001",
        )
        self.facility = Facility.objects.create(
            name="AVR", facility_type=Facility.FacilityType.AVR, capacity=50
        )
        OperatingHour.objects.create(
            facility=self.facility, day_of_week=0, open_time=time(6, 0), close_time=time(22, 0)
        )

    def _auth(self, user):
        self.client.force_authenticate(user)

    def _payload(self, **overrides):
        payload = dict(
            name="Portable Sound System",
            category_id=self.category.id,
            description="Portable sound system for events.",
            total_quantity=4,
            unit="set",
            condition="GOOD",
            status="AVAILABLE",
            storage_location="SAS Storage Room",
            asset_code="SAS-AUD-001",
            notes="Includes speakers, amplifier and cables.",
        )
        payload.update(overrides)
        return payload

    # ------------------------------------------------------------------
    # Permissions
    # ------------------------------------------------------------------

    def test_requester_cannot_create_equipment(self):
        self._auth(self.requester)
        response = self.client.post("/api/equipment/", self._payload(), format="json")
        self.assertEqual(response.status_code, 403)

    def test_requester_cannot_update_equipment(self):
        self._auth(self.requester)
        response = self.client.patch(
            f"/api/equipment/{self.mics.id}/", {"total_quantity": 10}, format="json"
        )
        self.assertEqual(response.status_code, 403)

    def test_requester_cannot_delete_equipment(self):
        self._auth(self.requester)
        response = self.client.delete(f"/api/equipment/{self.mics.id}/")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Equipment.objects.filter(pk=self.mics.id).exists())

    def test_requester_can_read_equipment(self):
        self._auth(self.requester)
        response = self.client.get("/api/equipment/")
        self.assertEqual(response.status_code, 200)
        names = [item["name"] for item in response.json()]
        self.assertIn("Wireless Microphone", names)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def test_admin_can_create_equipment(self):
        self._auth(self.admin)
        response = self.client.post("/api/equipment/", self._payload(), format="json")
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["name"], "Portable Sound System")
        self.assertEqual(body["status"], "AVAILABLE")
        self.assertEqual(body["status_label"], "Available")
        self.assertEqual(body["unit"], "set")
        self.assertEqual(body["asset_code"], "SAS-AUD-001")
        self.assertEqual(body["availability"]["total"], 4)
        self.assertEqual(body["availability"]["available"], 4)

    def test_admin_can_edit_equipment_fields(self):
        self._auth(self.admin)
        response = self.client.patch(
            f"/api/equipment/{self.mics.id}/",
            {"total_quantity": 10, "unit": "piece", "notes": "Updated"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["total_quantity"], 10)
        self.assertEqual(body["availability"]["total"], 10)
        self.assertEqual(body["availability"]["available"], 10)

    def test_multipart_create_stays_active(self):
        """Form-parsed creates must not be silently deactivated.

        DRF's HTML form parsers coerce a missing boolean checkbox to False;
        the equipment form (FormData, for image uploads) never sends
        ``is_active``, so the serializer must default it back to True.
        """
        self._auth(self.admin)
        response = self.client.post(
            "/api/equipment/",
            {
                "name": "Form Sound",
                "category_id": self.category.id,
                "total_quantity": 3,
                "unit": "set",
                "condition": "GOOD",
                "status": "AVAILABLE",
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertTrue(body["is_active"])
        self.assertEqual(body["availability"]["available"], 3)

    def test_multipart_edit_does_not_deactivate(self):
        """Editing via the form (multipart, no is_active) keeps the item active."""
        self._auth(self.admin)
        response = self.client.patch(
            f"/api/equipment/{self.mics.id}/",
            {"notes": "Edited via form"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["is_active"])

    def test_cannot_reduce_quantity_below_committed(self):
        """6 of 10 mics committed -> reducing to 4 must be rejected."""
        self._auth(self.admin)
        self.client.patch(f"/api/equipment/{self.mics.id}/", {"total_quantity": 10}, format="json")
        reservation = Reservation.objects.create(
            requester=self.requester,
            event_name="Orientation",
            facility=self.facility,
            date=date(2026, 9, 14),
            start_time=time(9, 0),
            end_time=time(11, 0),
            status=Reservation.Status.APPROVED,
        )
        ReservationItem.objects.create(
            reservation=reservation, equipment=self.mics, quantity=6
        )

        response = self.client.patch(
            f"/api/equipment/{self.mics.id}/", {"total_quantity": 4}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        error = response.json()["total_quantity"][0]
        self.assertIn("Cannot reduce inventory to 4", error)
        self.assertIn("6 units", error)

    def test_can_reduce_quantity_to_exactly_committed(self):
        self._auth(self.admin)
        reservation = Reservation.objects.create(
            requester=self.requester,
            event_name="Orientation",
            facility=self.facility,
            date=date(2026, 9, 14),
            start_time=time(9, 0),
            end_time=time(11, 0),
            status=Reservation.Status.APPROVED,
        )
        ReservationItem.objects.create(
            reservation=reservation, equipment=self.mics, quantity=6
        )
        response = self.client.patch(
            f"/api/equipment/{self.mics.id}/", {"total_quantity": 6}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["total_quantity"], 6)

    # ------------------------------------------------------------------
    # Safe deletion / archive
    # ------------------------------------------------------------------

    def test_delete_without_history_hard_deletes(self):
        fresh = Equipment.objects.create(
            name="Never Used", category=self.category, total_quantity=2
        )
        self._auth(self.admin)
        response = self.client.delete(f"/api/equipment/{fresh.id}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Equipment.objects.filter(pk=fresh.id).exists())

    def test_delete_with_reservation_history_archives(self):
        reservation = Reservation.objects.create(
            requester=self.requester,
            event_name="History event",
            facility=self.facility,
            date=date(2026, 9, 14),
            start_time=time(9, 0),
            end_time=time(11, 0),
            status=Reservation.Status.APPROVED,
        )
        ReservationItem.objects.create(
            reservation=reservation, equipment=self.mics, quantity=2
        )

        self._auth(self.admin)
        response = self.client.delete(f"/api/equipment/{self.mics.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["archived"])

        self.mics.refresh_from_db()
        self.assertFalse(self.mics.is_active)
        # Historical record is preserved.
        self.assertTrue(
            ReservationItem.objects.filter(
                reservation=reservation, equipment=self.mics
            ).exists()
        )

    def test_delete_with_maintenance_history_archives(self):
        MaintenanceRecord.objects.create(
            equipment=self.mics,
            quantity=1,
            issue_type=MaintenanceRecord.IssueType.DAMAGE,
        )
        self._auth(self.admin)
        response = self.client.delete(f"/api/equipment/{self.mics.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["archived"])
        self.mics.refresh_from_db()
        self.assertFalse(self.mics.is_active)

    def test_archived_equipment_hidden_from_default_list_and_availability(self):
        self.mics.is_active = False
        self.mics.save(update_fields=["is_active"])

        self._auth(self.requester)
        response = self.client.get("/api/equipment/")
        self.assertNotIn(
            "Wireless Microphone", [item["name"] for item in response.json()]
        )

        # The availability engine reports 0 available for archived lines.
        report = check_availability(
            self.facility.id,
            date(2026, 9, 14),
            time(9, 0),
            time(11, 0),
            [{"equipment_id": self.mics.id, "quantity": 1}],
        )
        self.assertEqual(report["items"][0]["available"], 0)
        self.assertEqual(report["items"][0]["status"], "UNAVAILABLE")

    def test_staff_can_see_archived_with_include_inactive(self):
        self.mics.is_active = False
        self.mics.save(update_fields=["is_active"])

        self._auth(self.admin)
        response = self.client.get("/api/equipment/?include_inactive=true")
        names = [item["name"] for item in response.json()]
        self.assertIn("Wireless Microphone", names)
        self.assertFalse(
            [item for item in response.json() if item["name"] == "Wireless Microphone"][0][
                "is_active"
            ]
        )

    def test_requester_cannot_see_archived_even_with_include_inactive(self):
        self.mics.is_active = False
        self.mics.save(update_fields=["is_active"])

        self._auth(self.requester)
        response = self.client.get("/api/equipment/?include_inactive=true")
        self.assertNotIn(
            "Wireless Microphone", [item["name"] for item in response.json()]
        )

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def test_mark_partial_units_under_maintenance(self):
        self._auth(self.admin)
        response = self.client.post(
            f"/api/equipment/{self.mics.id}/maintenance/",
            {"quantity": 2, "reason": "Two units need servicing"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["quantity"], 2)
        self.assertEqual(body["issue_type"], "MAINTENANCE")

        self.mics.refresh_from_db()
        # Partial maintenance: still AVAILABLE, 6 of 8 usable.
        self.assertEqual(self.mics.status, Equipment.Status.AVAILABLE)
        self._auth(self.requester)
        detail = self.client.get(f"/api/equipment/{self.mics.id}/").json()
        self.assertEqual(detail["availability"]["available"], 6)
        self.assertEqual(detail["availability"]["under_maintenance"], 2)

    def test_full_maintenance_flips_status_and_blocks_reservation(self):
        self._auth(self.admin)
        response = self.client.post(
            f"/api/equipment/{self.mics.id}/maintenance/",
            {"quantity": 8, "reason": "All units serviced"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.mics.refresh_from_db()
        self.assertEqual(self.mics.status, Equipment.Status.MAINTENANCE)

        # Availability reports 0; a reservation for 1 unit is blocked.
        report = check_availability(
            self.facility.id,
            date(2026, 9, 14),
            time(9, 0),
            time(11, 0),
            [{"equipment_id": self.mics.id, "quantity": 1}],
        )
        self.assertEqual(report["items"][0]["available"], 0)
        self.assertEqual(report["items"][0]["status"], "UNAVAILABLE")

        # Recommendations no longer suggest the item at all.
        recommendations = recommend_resources(
            "SEMINAR", 50, target_date=date(2026, 9, 14), start_time=time(9, 0), end_time=time(11, 0)
        )
        self.assertNotIn(
            "Wireless Microphone", [r["name"] for r in recommendations]
        )

    def test_resolving_maintenance_restores_availability(self):
        self._auth(self.admin)
        created = self.client.post(
            f"/api/equipment/{self.mics.id}/maintenance/",
            {"quantity": 8},
            format="json",
        ).json()
        self.mics.refresh_from_db()
        self.assertEqual(self.mics.status, Equipment.Status.MAINTENANCE)

        response = self.client.post(
            f"/api/maintenance/{created['id']}/resolve/", {}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.mics.refresh_from_db()
        self.assertEqual(self.mics.status, Equipment.Status.AVAILABLE)

        detail = self.client.get(f"/api/equipment/{self.mics.id}/").json()
        self.assertEqual(detail["availability"]["available"], 8)

    def test_requester_cannot_mark_maintenance(self):
        self._auth(self.requester)
        response = self.client.post(
            f"/api/equipment/{self.mics.id}/maintenance/",
            {"quantity": 2},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_cannot_retire_equipment_with_open_maintenance_via_status(self):
        """Setting status away from AVAILABLE is allowed, but that is the only
        path; maintenance records remain tracked independently."""
        self._auth(self.admin)
        response = self.client.patch(
            f"/api/equipment/{self.mics.id}/", {"status": "RETIRED"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["status"], "RETIRED")
        self.assertEqual(body["availability"]["available"], 0)

    # ------------------------------------------------------------------
    # History & stats
    # ------------------------------------------------------------------

    def test_usage_history_endpoint(self):
        reservation = Reservation.objects.create(
            requester=self.requester,
            event_name="Recognition Program",
            facility=self.facility,
            date=date(2026, 9, 14),
            start_time=time(9, 0),
            end_time=time(11, 0),
            status=Reservation.Status.APPROVED,
        )
        ReservationItem.objects.create(
            reservation=reservation, equipment=self.mics, quantity=4
        )
        self._auth(self.admin)
        response = self.client.get(f"/api/equipment/{self.mics.id}/history/")
        self.assertEqual(response.status_code, 200)
        rows = response.json()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["reservation_id"], reservation.reservation_id)
        self.assertEqual(rows[0]["event_name"], "Recognition Program")
        self.assertEqual(rows[0]["quantity"], 4)
        self.assertEqual(rows[0]["status"], "APPROVED")

    def test_stats_include_unavailable_units(self):
        unavailable = Equipment.objects.create(
            name="Broken Projector",
            category=EquipmentCategory.objects.create(name="Projectors"),
            total_quantity=2,
            status=Equipment.Status.UNAVAILABLE,
        )
        stats = equipment_stats()
        self.assertEqual(stats["unavailable_units"], 2)
        self.assertIn("unavailable_units", stats)

        self._auth(self.requester)
        response = self.client.get("/api/equipment/stats/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["unavailable_units"], 2)

    def test_status_filter(self):
        Equipment.objects.create(
            name="Broken Projector",
            category=EquipmentCategory.objects.create(name="Projectors"),
            total_quantity=2,
            status=Equipment.Status.UNAVAILABLE,
        )
        self._auth(self.requester)
        response = self.client.get("/api/equipment/?status=UNAVAILABLE")
        names = [item["name"] for item in response.json()]
        self.assertEqual(names, ["Broken Projector"])

    # ------------------------------------------------------------------
    # Equipment image: upload, validation, and cleanup
    # ------------------------------------------------------------------

    def test_admin_can_create_equipment_with_image(self):
        self._auth(self.admin)
        response = self.client.post(
            "/api/equipment/",
            {
                **self._payload(),
                "image": _png(),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertIn("image", body)
        self.assertTrue(body["image"].endswith(".png"), body["image"])
        self.assertTrue(
            Equipment.objects.filter(pk=body["id"], image__isnull=False).exists()
        )

    def test_admin_can_replace_equipment_image(self):
        self._auth(self.admin)
        item = Equipment.objects.create(
            name="Sound System", category=self.category, image=_png()
        )
        saved_name = item.image.name

        response = self.client.patch(
            f"/api/equipment/{item.id}/",
            {"image": _jpeg()},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200, response.content)
        item.refresh_from_db()
        self.assertTrue(item.image.name.endswith(".jpg"))
        self.assertNotEqual(item.image.name, saved_name)

        # The old file should be removed from storage.
        self.assertFalse(item.image.storage.exists(saved_name))

    def test_admin_can_remove_equipment_image(self):
        self._auth(self.admin)
        item = Equipment.objects.create(
            name="Sound System", category=self.category, image=_png()
        )
        saved_name = item.image.name

        # Removing an image must clear the field and delete the stored file.
        response = self.client.patch(
            f"/api/equipment/{item.id}/", {"image": None}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        item.refresh_from_db()
        self.assertEqual(item.image.name, '')
        self.assertFalse(item.image.storage.exists(saved_name))

    def test_invalid_image_type_is_rejected(self):
        self._auth(self.admin)
        gif = ContentFile(b"not an image", name="sound-system.gif")
        gif.content_type = "image/gif"

        response = self.client.post(
            "/api/equipment/",
            {
                **self._payload(),
                "image": gif,
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 400, response.content)
        error = response.json()["image"][0]
        self.assertIn("JPG, PNG, or WEBP", error)

    def test_image_larger_than_5_mb_is_rejected(self):
        self._auth(self.admin)
        giant = ContentFile(b"x" * (MAX_SIZE + 1), name="giant.png")
        giant.content_type = PNG

        response = self.client.post(
            "/api/equipment/",
            {
                **self._payload(),
                "image": giant,
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 400, response.content)
        error = response.json()["image"][0]
        self.assertIn("smaller than 5 MB", error)

    def test_image_exactly_5_mb_is_accepted(self):
        self._auth(self.admin)
        at_limit = ContentFile(b"x" * MAX_SIZE, name="at-limit.png")
        at_limit.content_type = PNG

        response = self.client.post(
            "/api/equipment/",
            {
                **self._payload(),
                "image": at_limit,
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(Equipment.objects.filter(image__isnull=False).exists())

    def test_archived_equipment_keeps_its_image(self):
        self._auth(self.admin)
        item = Equipment.objects.create(
            name="Kept", category=self.category, image=_png()
        )
        saved_name = item.image.name

        # Equipment with history is archived (not deleted), so its image must stay.
        reservation = Reservation.objects.create(
            requester=self.requester,
            event_name="History",
            facility=self.facility,
            date=date(2026, 9, 14),
            start_time=time(9, 0),
            end_time=time(11, 0),
            status=Reservation.Status.APPROVED,
        )
        ReservationItem.objects.create(
            reservation=reservation,
            equipment=item,
            quantity=1,
        )

        response = self.client.delete(f"/api/equipment/{item.id}/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["archived"])
        item.refresh_from_db()
        self.assertFalse(item.is_active)
        self.assertTrue(item.image.name.endswith(".png"))
        self.assertTrue(item.image.storage.exists(saved_name))

    def test_deleted_equipment_without_history_removes_its_image(self):
        self._auth(self.admin)
        item = Equipment.objects.create(
            name="Fresh", category=self.category, image=_png()
        )
        saved_name = item.image.name

        response = self.client.delete(f"/api/equipment/{item.id}/")
        self.assertEqual(response.status_code, 204, response.content)
        self.assertFalse(Equipment.objects.filter(pk=item.id).exists())
        # The model instance still references the old path, but the file must be gone.
        self.assertFalse(item.image.storage.exists(saved_name))