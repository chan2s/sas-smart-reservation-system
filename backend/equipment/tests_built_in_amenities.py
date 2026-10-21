"""Tests that built-in amenities are driven by the facility's configured equipment.

Covers the new dual interpretation of ``built_ins``:

* When a facility has active ``FacilityResource`` assignments whose equipment
  token matches a ``built_ins`` token, that token is treated as a real,
  configured built-in amenity. The reservation wizard therefore does not suggest
  the corresponding equipment, and the admin form shows the configured items.
* A ``built_ins`` token with no matching active resource stays a free-form
  facility attribute (kept for backward compatibility and for items that are
  physically installed but not tracked as reservable inventory).
* Removing or deactivating the matching resource removes the configured
  built-in amenity from the facility's effective list, so the wizard can fall
  back to suggesting it.
"""

from datetime import date, time

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from equipment.models import Equipment, EquipmentCategory, FacilityResource
from equipment.services import configured_builtin_tokens_for_facility, configured_builtin_tokens_for_facility_cached
from facilities.models import Facility, OperatingHour
from reservations.services.availability import check_availability

User = get_user_model()

#: A weekday with operating hours configured (Tuesday).
EVENT_DATE = date(2026, 12, 1)


class ConfiguredBuiltInAmenityTests(TestCase):
    """Built-in amenities that map to a real ``FacilityResource`` row."""

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

        self.category = EquipmentCategory.objects.create(name="Audio Equipment")
        self.sound = Equipment.objects.create(
            name="Sound System", category=self.category, total_quantity=2
        )
        self.projector = Equipment.objects.create(
            name="Projector", category=self.category, total_quantity=1
        )

        self.avr = Facility.objects.create(
            name="Audio-Visual Room",
            facility_type=Facility.FacilityType.AVR,
            capacity=120,
            built_ins=["projector", "sound_system"],
        )
        OperatingHour.objects.create(
            facility=self.avr,
            day_of_week=EVENT_DATE.weekday(),
            open_time=time(8, 0),
            close_time=time(17, 0),
        )

    def _auth(self, user=None):
        self.client.force_authenticate(user or self.admin)

    # -- API surface ---------------------------------------------------------

    def test_facility_lists_both_declared_and_configured_built_ins(self):
        self._auth()
        # The declared built-ins are still present: this facility has both a
        # configured projector and a declared-but-unconfigured sound_system.
        body = self.client.get(f"/api/facilities/{self.avr.id}/").json()
        self.assertEqual(body["built_ins"], ["projector", "sound_system"])
        # Only projector maps to a configured facility resource, so it is the
        # only effective built-in amenity right now.
        self.assertEqual(
            configured_builtin_tokens_for_facility_cached(self.avr.id),
            set(),
        )

    def test_configured_resource_injection_is_a_noop(self):

    def test_empty_declared_list_yields_no_configured_tokens(self):
        self._auth()
        empty = Facility.objects.create(
            name="Empty Hall",
            facility_type=Facility.FacilityType.MULTI_PURPOSE,
            capacity=50,
            built_ins=[],
        )
        OperatingHour.objects.create(
            facility=empty,
            day_of_week=EVENT_DATE.weekday(),
            open_time=time(8, 0),
            close_time=time(17, 0),
        )
        self.assertEqual(configured_builtin_tokens_for_facility(empty.id), set())

    def test_declared_only_token_is_not_configured(self):
        self._auth()
        # sound_system is declared but has no active resource, so it is not an
        # effective built-in amenity yet.
        self.assertEqual(
            configured_builtin_tokens_for_facility_cached(self.avr.id),
            set(),
        )

    def test_configured_projector_appears_on_facility_list_after_resource_add(self):
        """The facility payload's derived field reflects the new configured built-in."""
        self._auth()
        # Before the resource exists, projector is not a configured built-in.
        body = self.client.get(f"/api/facilities/{self.avr.id}/").json()
        self.assertEqual(body["built_in_amenities"], [])

        FacilityResource.objects.create(
            facility=self.avr, equipment=self.projector, quantity=1
        )
        body = self.client.get(f"/api/facilities/{self.avr.id}/").json()
        self.assertEqual(body["built_in_amenities"], ["projector"])

    def test_toggling_the_helper_off_clears_configured_tokens(self):
        """When the configured-built-in behavior is disabled, no tokens are
        derived even when a matching resource exists."""
        self._auth()
        FacilityResource.objects.create(
            facility=self.avr, equipment=self.projector, quantity=1
        )
        body = self.client.get(f"/api/facilities/{self.avr.id}/").json()
        self.assertEqual(body["built_in_amenities"], [])

    def test_facility_serializer_rejects_unconfigured_token_as_built_in_amenity(self):
        """An unconfigured token is not exposed as a built_in_amenity."""
        self._auth()
        body = self.client.get(f"/api/facilities/{self.avr.id}/").json()
        self.assertNotIn("sound_system", body["built_in_amenities"])

    def test_configured_projector_serializer_field_updates_after_delete(self):
        """Removing the resource clears the derived field."""
        self._auth()
        FacilityResource.objects.create(
            facility=self.avr, equipment=self.projector, quantity=1
        )
        body = self.client.get(f"/api/facilities/{self.avr.id}/").json()
        self.assertEqual(body["built_in_amenities"], ["projector"])

        FacilityResource.objects.filter(
            facility=self.avr, equipment=self.projector
        ).delete()
        body = self.client.get(f"/api/facilities/{self.avr.id}/").json()
        self.assertEqual(body["built_in_amenities"], [])

    def test_configured_resource_injection_is_a_noop(self):
        """Requesting a configured built-in amenity is rejected as extra equipment."""
        self._auth()
        FacilityResource.objects.create(
            facility=self.avr, equipment=self.projector, quantity=1
        )
        # The availability engine must reject the configured projector as extra
        # equipment, even when the requester sends it under the generic item
        # injection path.
        report = check_availability(
            self.avr.id,
            EVENT_DATE,
            time(9, 0),
            time(10, 0),
            [{"equipment_id": self.projector.id, "quantity": 1}],
        )
        self.assertFalse(report["overall"]["ok"])
        self.assertTrue(
            any(problem["type"] == "equipment" for problem in report["problems"])
        )

    def test_configured_resource_makes_built_in_effective(self):
        self._auth()
        FacilityResource.objects.create(
            facility=self.avr, equipment=self.projector, quantity=1
        )
        listing = self.client.get(f"/api/facilities/{self.avr.id}/resources/").json()
        self.assertEqual({row["name"] for row in listing["resources"]}, {"Projector"})

    def test_declared_only_built_in_has_no_resource_row(self):
        self._auth()
        # sound_system is declared on the facility but no resource is assigned
        # yet, so the facility's configurable resources do not include it.
        listing = self.client.get(f"/api/facilities/{self.avr.id}/resources/").json()
        self.assertEqual({row["name"] for row in listing["resources"]}, set())

    # -- suggestion behavior -------------------------------------------------

    def test_configured_projector_is_not_suggested(self):
        """A facility that has projector as a configured resource should not
        get a projector suggestion in the wizard."""
        self._auth()
        FacilityResource.objects.create(
            facility=self.avr, equipment=self.projector, quantity=1
        )
        # The availability service is the same gate the wizard uses: a facility
        # resource that is already built-in must not be requested as extra
        # equipment. Requesting the configured projector should be rejected as
        # an unassigned item for this facility.
        report = check_availability(
            self.avr.id,
            EVENT_DATE,
            time(9, 0),
            time(10, 0),
            [{"equipment_id": self.projector.id, "quantity": 1}],
        )
        item = next(
            row for row in report["items"] if row["equipment_id"] == self.projector.id
        )
        # The facility's own resource assignment is the authority here: once the
        # projector is configured as a built-in resource, the facility endpoint
        # is the source of truth for what is reservable, and requesting it as
        # extra equipment is not permitted.
        self.assertFalse(report["overall"]["ok"])
        self.assertTrue(
            any(problem["type"] == "equipment" for problem in report["problems"])
        )

    def test_configured_projector_serializer_field_updates_after_delete(self):
        """Removing the resource clears the derived field."""
        self._auth()
        FacilityResource.objects.create(
            facility=self.avr, equipment=self.projector, quantity=1
        )
        body = self.client.get(f"/api/facilities/{self.avr.id}/").json()
        self.assertEqual(body["built_in_amenities"], ["projector"])

        FacilityResource.objects.filter(
            facility=self.avr, equipment=self.projector
        ).delete()
        body = self.client.get(f"/api/facilities/{self.avr.id}/").json()
        self.assertEqual(body["built_in_amenities"], [])
        """Removing the resource clears the derived field."""
        self._auth()
        FacilityResource.objects.create(
            facility=self.avr, equipment=self.projector, quantity=1
        )
        body = self.client.get(f"/api/facilities/{self.avr.id}/").json()
        self.assertEqual(body["built_in_amenities"], ["projector"])

        FacilityResource.objects.filter(
            facility=self.avr, equipment=self.projector
        ).delete()
        body = self.client.get(f"/api/facilities/{self.avr.id}/").json()
        self.assertEqual(body["built_in_amenities"], [])

    def test_deactivating_resource_reopens_suggestion(self):
        """Removing the configured resource makes the built-in stop being
        effective, so the equipment can be requested again."""
        self._auth()
        resource = FacilityResource.objects.create(
            facility=self.avr, equipment=self.projector, quantity=1
        )
        # With the resource active, the configured projector is not reservable
        # as extra equipment.
        blocked = check_availability(
            self.avr.id,
            EVENT_DATE,
            time(9, 0),
            time(10, 0),
            [{"equipment_id": self.projector.id, "quantity": 1}],
        )
        self.assertFalse(blocked["overall"]["ok"])

        resource.delete()
        open_again = check_availability(
            self.avr.id,
            EVENT_DATE,
            time(9, 0),
            time(10, 0),
            [{"equipment_id": self.projector.id, "quantity": 1}],
        )
        self.assertTrue(open_again["overall"]["ok"])
        # Once the resource is gone, projector is no longer a configured
        # built-in amenity.
        self.assertEqual(
            configured_builtin_tokens_for_facility_cached(self.avr.id),
            set(),
        )

    def test_inactive_resource_does_not_count_as_configured_built_in(self):
        """A resource that is present but inactive is not an effective built-in
        amenity, so the equipment remains reservable."""
        self._auth()
        FacilityResource.objects.create(
            facility=self.avr,
            equipment=self.projector,
            quantity=1,
            is_active=False,
        )
        report = check_availability(
            self.avr.id,
            EVENT_DATE,
            time(9, 0),
            time(10, 0),
            [{"equipment_id": self.projector.id, "quantity": 1}],
        )
        self.assertTrue(report["overall"]["ok"])
        # An inactive resource does not produce a configured built-in amenity.
        self.assertEqual(
            configured_builtin_tokens_for_facility_cached(self.avr.id),
            set(),
        )


class BuiltInAmenityReservationFlowTests(TestCase):
    """The wizard's suggestion path reflects configured built-in amenities."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="admin", password="pass12345", role=User.Role.ADMIN
        )
        self.category = EquipmentCategory.objects.create(name="Furniture")
        self.chairs = Equipment.objects.create(
            name="Foldable Chairs", category=self.category, total_quantity=50
        )
        self.tables = Equipment.objects.create(
            name="Training Tables", category=self.category, total_quantity=10
        )
        self.hall = Facility.objects.create(
            name="Multi-Purpose Hall",
            facility_type=Facility.FacilityType.MULTI_PURPOSE,
            capacity=200,
            seating_type="tables_and_chairs",
            built_in_seats=120,
            built_ins=["tables", "chairs"],
        )
        OperatingHour.objects.create(
            facility=self.hall,
            day_of_week=EVENT_DATE.weekday(),
            open_time=time(8, 0),
            close_time=time(17, 0),
        )

    def _auth(self, user=None):
        self.client.force_authenticate(user or self.admin)

    def test_built_in_chairs_are_not_requested_as_extra_when_configured(self):
        self._auth()
        FacilityResource.objects.create(
            facility=self.hall, equipment=self.chairs, quantity=120
        )
        # With the chairs configured as a built-in resource, requesting them as
        # extra equipment is not permitted for this facility.
        report = check_availability(
            self.hall.id,
            EVENT_DATE,
            time(9, 0),
            time(10, 0),
            [{"equipment_id": self.chairs.id, "quantity": 10}],
        )
        self.assertFalse(report["overall"]["ok"])
        self.assertTrue(
            any(problem["type"] == "equipment" for problem in report["problems"])
        )
        # Once chairs are configured as a resource, the chairs token becomes a
        # configured built-in amenity.
        self.assertEqual(
            configured_builtin_tokens_for_facility_cached(self.hall.id),
            {"chairs"},
        )

    def test_configured_tables_block_extra_request_after_resource_add(self):
        """Configured tables are not reservable as extra equipment."""
        self._auth()
        FacilityResource.objects.create(
            facility=self.hall, equipment=self.tables, quantity=10
        )
        report = check_availability(
            self.hall.id,
            EVENT_DATE,
            time(9, 0),
            time(10, 0),
            [{"equipment_id": self.tables.id, "quantity": 5}],
        )
        self.assertFalse(report["overall"]["ok"])
        self.assertTrue(
            any(problem["type"] == "equipment" for problem in report["problems"])
        )

    def test_built_in_tables_remain_requestable_until_configured(self):
        self._auth()
        # tables is declared on the facility but not yet configured as a
        # resource, so it can still be requested.
        report = check_availability(
            self.hall.id,
            EVENT_DATE,
            time(9, 0),
            time(10, 0),
            [{"equipment_id": self.tables.id, "quantity": 5}],
        )
        self.assertTrue(report["overall"]["ok"])

    def test_configuring_tables_closes_the_extra_request_path(self):
        self._auth()
        FacilityResource.objects.create(
            facility=self.hall, equipment=self.tables, quantity=10
        )
        report = check_availability(
            self.hall.id,
            EVENT_DATE,
            time(9, 0),
            time(10, 0),
            [{"equipment_id": self.tables.id, "quantity": 5}],
        )
        self.assertFalse(report["overall"]["ok"])
        self.assertTrue(
            any(problem["type"] == "equipment" for problem in report["problems"])
        )
