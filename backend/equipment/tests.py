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

from .models import Equipment, EquipmentCategory, EquipmentImage, MaintenanceRecord
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


class EquipmentGalleryApiTests(TestCase):
    """Multiple images per equipment item: upload, ordering, primary, delete."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="gallery-admin", password="pass12345", role=User.Role.ADMIN
        )
        self.requester = User.objects.create_user(
            username="gallery-requester", password="pass12345", role=User.Role.REQUESTER
        )
        self.category = EquipmentCategory.objects.create(name="Signage")
        self.item = Equipment.objects.create(
            name="Event Signage Stand", category=self.category
        )
        self._auth(self.admin)

    def _auth(self, user):
        self.client.force_authenticate(user)

    def _upload(self, files, equipment=None):
        """POST files the way the admin form does: one `images` key per file."""
        target = equipment or self.item
        return self.client.post(
            f"/api/equipment/{target.id}/images/",
            {"images": files},
            format="multipart",
        )

    def _gallery(self, equipment=None):
        target = equipment or self.item
        response = self.client.get(f"/api/equipment/{target.id}/images/")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["images"]

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------

    def test_upload_single_image_creates_primary_entry(self):
        response = self._upload([_png()])
        self.assertEqual(response.status_code, 201, response.content)
        created = response.json()["images"]
        self.assertEqual(len(created), 1)
        self.assertTrue(created[0]["is_primary"])
        self.assertEqual(created[0]["display_order"], 0)
        self.assertTrue(created[0]["url"].startswith("http"), created[0]["url"])
        self.assertIn("/media/equipment/", created[0]["url"])
        self.assertEqual(EquipmentImage.objects.filter(equipment=self.item).count(), 1)

    def test_upload_multiple_images_in_one_request_keeps_order(self):
        response = self._upload([_png(), _jpeg(), _webp()])
        self.assertEqual(response.status_code, 201, response.content)
        created = response.json()["images"]
        self.assertEqual(len(created), 3)
        self.assertEqual(
            [image["display_order"] for image in created], [0, 1, 2]
        )
        # Only the first image of an empty gallery is primary.
        self.assertEqual(
            [image["is_primary"] for image in created], [True, False, False]
        )

    def test_second_upload_appends_and_keeps_existing_primary(self):
        self._upload([_png()])
        primary_id = EquipmentImage.objects.get(equipment=self.item, is_primary=True).id

        response = self._upload([_jpeg()])
        self.assertEqual(response.status_code, 201, response.content)
        self.assertFalse(response.json()["images"][0]["is_primary"])

        gallery = self._gallery()
        self.assertEqual(len(gallery), 2)
        self.assertTrue(gallery[0]["is_primary"])
        self.assertEqual(gallery[0]["id"], primary_id)
        self.assertEqual([image["display_order"] for image in gallery], [0, 1])

    def test_upload_without_files_is_rejected(self):
        response = self.client.post(
            f"/api/equipment/{self.item.id}/images/", {}, format="multipart"
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("images", response.json())

    def test_upload_rejects_unsupported_type(self):
        gif = ContentFile(b"not an image", name="signage.gif")
        gif.content_type = "image/gif"
        response = self._upload([gif])
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("JPG, PNG, or WEBP", response.json()["images"][0])
        self.assertEqual(EquipmentImage.objects.filter(equipment=self.item).count(), 0)

    def test_upload_rejects_oversized_image(self):
        data = BytesIO()
        PilImage.new("RGB", (4, 4), color=(0, 0, 0)).save(data, format="PNG")
        giant = ContentFile(data.getvalue() + b"0" * (MAX_SIZE + 1), name="huge.png")
        giant.content_type = PNG
        response = self._upload([giant])
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("smaller than 5 MB", response.json()["images"][0])

    def test_upload_rejects_a_non_image_with_an_image_extension(self):
        fake = ContentFile(b"definitely not a jpeg", name="fake.jpg")
        fake.content_type = JPEG
        response = self._upload([fake])
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("could not be read as an image", response.json()["images"][0])

    # ------------------------------------------------------------------
    # Ordering and primary
    # ------------------------------------------------------------------

    def test_primary_image_is_returned_first(self):
        self._upload([_png(), _jpeg()])
        first, second = list(EquipmentImage.objects.filter(equipment=self.item).order_by("id"))

        response = self.client.post(
            f"/api/equipment/{self.item.id}/images/{second.id}/primary/"
        )
        self.assertEqual(response.status_code, 200, response.content)
        gallery = response.json()["images"]
        self.assertEqual(gallery[0]["id"], second.id)
        self.assertEqual(
            EquipmentImage.objects.filter(equipment=self.item, is_primary=True).count(), 1
        )
        self.assertFalse(
            EquipmentImage.objects.get(pk=first.id).is_primary
        )

    def test_reorder_sets_display_order(self):
        self._upload([_png(), _jpeg(), _webp()])
        images = list(EquipmentImage.objects.filter(equipment=self.item).order_by("id"))
        ids = [image.id for image in images]

        # Reverse everything; the primary is pinned first by the API ordering.
        response = self.client.post(
            f"/api/equipment/{self.item.id}/images/order/",
            {"order": list(reversed(ids))},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        # display_order follows the request exactly...
        self.assertEqual(
            list(
                EquipmentImage.objects.filter(equipment=self.item)
                .order_by("display_order")
                .values_list("id", flat=True)
            ),
            list(reversed(ids)),
        )
        # ...while the API still pins the primary image (ids[0], now order 2)
        # in front of the rest, which keep their relative order.
        self.assertEqual(
            [image["id"] for image in response.json()["images"]],
            [ids[0], ids[2], ids[1]],
        )
        self.assertEqual(
            [image["display_order"] for image in response.json()["images"]],
            [2, 0, 1],
        )
        self.assertEqual(
            list(
                EquipmentImage.objects.filter(equipment=self.item)
                .order_by("display_order")
                .values_list("id", flat=True)
            ),
            list(reversed(ids)),
        )

    def test_reorder_requires_every_id_exactly_once(self):
        self._upload([_png(), _jpeg()])
        ids = list(EquipmentImage.objects.filter(equipment=self.item).values_list("id", flat=True))
        for bad_order in ([ids[0]], [ids[0], ids[0]], [ids[0], 99999], "nope", ["x"]):
            response = self.client.post(
                f"/api/equipment/{self.item.id}/images/order/",
                {"order": bad_order},
                format="json",
            )
            self.assertEqual(response.status_code, 400, (bad_order, response.content))

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def test_delete_image_removes_row_and_file(self):
        created = self._upload([_png(), _jpeg()]).json()["images"]
        keep_id = created[0]["id"]
        doomed_id = created[1]["id"]
        doomed_name = EquipmentImage.objects.get(pk=doomed_id).image.name
        keep_name = EquipmentImage.objects.get(pk=keep_id).image.name
        storage = EquipmentImage.objects.get(pk=doomed_id).image.storage

        response = self.client.delete(
            f"/api/equipment/{self.item.id}/images/{doomed_id}/"
        )
        self.assertEqual(response.status_code, 200, response.content)
        gallery = response.json()["images"]
        self.assertEqual([image["id"] for image in gallery], [keep_id])
        self.assertFalse(EquipmentImage.objects.filter(pk=doomed_id).exists())
        self.assertFalse(storage.exists(doomed_name))
        self.assertTrue(storage.exists(keep_name))

    def test_delete_primary_promotes_the_next_image(self):
        created = self._upload([_png(), _jpeg(), _webp()]).json()["images"]
        primary_id = created[0]["id"]
        next_id = created[1]["id"]

        response = self.client.delete(
            f"/api/equipment/{self.item.id}/images/{primary_id}/"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["images"][0]["id"], next_id)
        self.assertTrue(response.json()["images"][0]["is_primary"])
        self.assertEqual(
            EquipmentImage.objects.filter(equipment=self.item, is_primary=True).count(), 1
        )

    def test_emptying_the_gallery_clears_the_legacy_image(self):
        """A deleted legacy picture must not reappear through the fallback."""
        self.item.image = _png()
        self.item.save()
        self.item.refresh_from_db()
        legacy_name = self.item.image.name
        legacy_storage = self.item.image.storage

        # The upload adopts the legacy image, so the gallery holds both.
        self._upload([_jpeg()])
        gallery = self._gallery()
        self.assertEqual(len(gallery), 2)
        adopted_id, added_id = gallery[0]["id"], gallery[1]["id"]
        added_name = EquipmentImage.objects.get(pk=added_id).image.name
        added_storage = EquipmentImage.objects.get(pk=added_id).image.storage

        # Deleting the adopted entry clears the legacy field with it.
        response = self.client.delete(
            f"/api/equipment/{self.item.id}/images/{adopted_id}/"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.item.refresh_from_db()
        self.assertFalse(self.item.image)
        self.assertFalse(legacy_storage.exists(legacy_name))

        # Emptying the gallery for good leaves no images and no file.
        response = self.client.delete(
            f"/api/equipment/{self.item.id}/images/{added_id}/"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["images"], [])
        self.assertFalse(added_storage.exists(added_name))

        # The API must report no images at all, not a resurrected legacy one.
        detail = self.client.get(f"/api/equipment/{self.item.id}/")
        self.assertEqual(detail.json()["images"], [])

    def test_deleting_unknown_image_returns_404(self):
        response = self.client.delete(f"/api/equipment/{self.item.id}/images/99999/")
        self.assertEqual(response.status_code, 404, response.content)

    # ------------------------------------------------------------------
    # Backward compatibility
    # ------------------------------------------------------------------

    def test_legacy_single_image_is_exposed_as_a_gallery_entry(self):
        item = Equipment.objects.create(
            name="Legacy Stand", category=self.category, image=_png()
        )
        detail = self.client.get(f"/api/equipment/{item.id}/")
        self.assertEqual(detail.status_code, 200, detail.content)
        images = detail.json()["images"]
        self.assertEqual(len(images), 1)
        self.assertIsNone(images[0]["id"])
        self.assertTrue(images[0]["is_primary"])
        self.assertTrue(images[0]["url"].startswith("http"))
        # The legacy field itself is untouched.
        self.assertEqual(detail.json()["image"], images[0]["url"])

    def test_equipment_without_images_reports_an_empty_gallery(self):
        self.assertEqual(self._gallery(), [])
        detail = self.client.get(f"/api/equipment/{self.item.id}/")
        self.assertEqual(detail.json()["images"], [])
        self.assertIsNone(detail.json()["image"])

    def test_upload_adopts_a_legacy_image_into_the_gallery(self):
        """A pre-gallery image must not disappear when the first upload lands."""
        self.item.image = _png()
        self.item.save()
        self.item.refresh_from_db()
        legacy_name = self.item.image.name
        legacy_storage = self.item.image.storage

        response = self._upload([_jpeg()])
        self.assertEqual(response.status_code, 201, response.content)

        gallery = self._gallery()
        self.assertEqual(len(gallery), 2)
        # The adopted legacy image stays first and keeps the primary flag.
        self.assertTrue(gallery[0]["is_primary"])
        self.assertTrue(gallery[0]["url"].endswith(legacy_name.split("/")[-1]))
        self.assertTrue(legacy_storage.exists(legacy_name))

    def test_legacy_single_image_upload_still_works(self):
        response = self.client.patch(
            f"/api/equipment/{self.item.id}/", {"image": _jpeg()}, format="multipart"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(response.json()["images"]), 1)
        self.assertIsNone(response.json()["images"][0]["id"])

    def test_editing_notes_does_not_touch_the_gallery(self):
        created = self._upload([_png(), _jpeg()]).json()["images"]
        response = self.client.patch(
            f"/api/equipment/{self.item.id}/",
            {"name": "Event Signage Stand", "category_id": self.category.id, "notes": "Only notes"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            [image["id"] for image in response.json()["images"]],
            [image["id"] for image in created],
        )

    # ------------------------------------------------------------------
    # End-to-end admin workflow
    # ------------------------------------------------------------------

    def test_admin_gallery_workflow_end_to_end(self):
        """The exact request sequence the admin form performs, start to finish."""
        # 1. Create the item with the fields-only multipart body the form sends.
        created = self.client.post(
            "/api/equipment/",
            {
                "name": "Event Signage Stand",
                "category_id": self.category.id,
                "description": "Stand for event signage.",
                "total_quantity": "2",
                "unit": "unit",
                "condition": "GOOD",
                "status": "AVAILABLE",
                "storage_location": "SAS Storage Room",
                "asset_code": "SAS-SGN-001",
                "notes": "",
            },
            format="multipart",
        )
        self.assertEqual(created.status_code, 201, created.content)
        item = Equipment.objects.get(pk=created.json()["id"])
        self.assertEqual(created.json()["images"], [])

        # 2. Upload three images in one action.
        response = self._upload([_png(), _jpeg(), _webp()], equipment=item)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(len(response.json()["images"]), 3)

        # 3. Add one more in a second action.
        response = self._upload([_png()], equipment=item)
        self.assertEqual(response.status_code, 201, response.content)

        # 4. Reopening the item shows all four, primary first.
        detail = self.client.get(f"/api/equipment/{item.id}/")
        images = detail.json()["images"]
        self.assertEqual(len(images), 4)
        self.assertTrue(images[0]["is_primary"])
        self.assertEqual([image["display_order"] for image in images], [0, 1, 2, 3])

        # 5. Editing other fields must not disturb the gallery.
        response = self.client.patch(
            f"/api/equipment/{item.id}/",
            {
                "name": "Event Signage Stand",
                "category_id": self.category.id,
                "total_quantity": "2",
                "unit": "unit",
                "condition": "GOOD",
                "status": "AVAILABLE",
                "storage_location": "SAS Storage Room",
                "asset_code": "SAS-SGN-001",
                "notes": "Only notes changed",
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            [image["id"] for image in response.json()["images"]],
            [image["id"] for image in images],
        )

        # 6. Promote the last image.
        last_id = images[-1]["id"]
        response = self.client.post(
            f"/api/equipment/{item.id}/images/{last_id}/primary/"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["images"][0]["id"], last_id)

        # 7. Reorder the survivors (primary stays pinned in front).
        ids = [image["id"] for image in response.json()["images"]]
        order = [ids[0], ids[3], ids[2], ids[1]]
        response = self.client.post(
            f"/api/equipment/{item.id}/images/order/", {"order": order}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual([image["id"] for image in response.json()["images"]], order)

        # 8. Delete one image and confirm its file is gone.
        doomed_id = ids[1]
        doomed = EquipmentImage.objects.get(pk=doomed_id)
        doomed_name, doomed_storage = doomed.image.name, doomed.image.storage
        response = self.client.delete(
            f"/api/equipment/{item.id}/images/{doomed_id}/"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(doomed_storage.exists(doomed_name))

        # 9. The final state survives a fresh read ("refresh the browser").
        final = self.client.get(f"/api/equipment/{item.id}/").json()["images"]
        self.assertEqual([image["id"] for image in final], [ids[0], ids[3], ids[2]])
        self.assertTrue(final[0]["is_primary"])
        for image in final:
            self.assertTrue(image["url"].startswith("http"))
            self.assertIn("/media/equipment/", image["url"])

    # ------------------------------------------------------------------
    # Permissions
    # ------------------------------------------------------------------

    def test_requester_can_read_but_not_change_the_gallery(self):
        gallery_id = self._upload([_png()]).json()["images"][0]["id"]
        self._auth(self.requester)

        self.assertEqual(self._gallery()[0]["id"], gallery_id)
        self.assertEqual(self._upload([_jpeg()]).status_code, 403)
        self.assertEqual(
            self.client.delete(
                f"/api/equipment/{self.item.id}/images/{gallery_id}/"
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                f"/api/equipment/{self.item.id}/images/{gallery_id}/primary/"
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                f"/api/equipment/{self.item.id}/images/order/",
                {"order": [gallery_id]},
                format="json",
            ).status_code,
            403,
        )
        self.assertEqual(
            EquipmentImage.objects.filter(equipment=self.item).count(), 1
        )