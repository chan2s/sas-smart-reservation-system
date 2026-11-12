from datetime import date, time
from decimal import Decimal
from importlib import import_module
from uuid import uuid4

from django.test import TestCase

from equipment.models import Equipment, EquipmentCategory
from facilities.models import Facility
from reservations.models import Reservation, ReservationFee, ReservationItem


class UnifiedCatalogMigrationTests(TestCase):
    def test_duplicate_item_merge_preserves_request_and_financial_snapshots(self):
        suffix = uuid4().hex
        category = EquipmentCategory.objects.create(name=f"Migration Test {suffix}")
        canonical = Equipment.objects.create(name=f"Canonical {suffix}", category=category)
        duplicate = Equipment.objects.create(name=f"Duplicate {suffix}", category=category)
        facility, _ = Facility.objects.get_or_create(
            name="Gymnasium", defaults={"facility_type": Facility.FacilityType.GYMNASIUM}
        )
        reservation = Reservation.objects.create(
            event_name="Historical reservation",
            facility=facility,
            date=date(2026, 11, 14),
            start_time=time(8),
            end_time=time(17),
            requester_type=Reservation.RequesterType.EXTERNAL,
            estimated_total=Decimal("6500.00"),
        )
        canonical_item = ReservationItem.objects.create(
            reservation=reservation,
            equipment=canonical,
            quantity=1,
            operator_requested=False,
            returned=True,
        )
        duplicate_item = ReservationItem.objects.create(
            reservation=reservation,
            equipment=duplicate,
            quantity=2,
            operator_requested=True,
            returned=False,
        )
        fee = ReservationFee.objects.create(
            reservation=reservation,
            fee_type=ReservationFee.FeeType.EQUIPMENT,
            description="Stage Sound System (historical rate)",
            quantity=Decimal("1.00"),
            unit="unit",
            unit_price=Decimal("1000.00"),
            subtotal=Decimal("1000.00"),
        )

        migration = import_module("reservations.migrations.0027_unified_rental_catalog")
        migration.merge_reservation_items(
            ReservationItem,
            duplicate_equipment_id=duplicate.pk,
            canonical_equipment_id=canonical.pk,
            db="default",
        )

        canonical_item.refresh_from_db()
        self.assertEqual(canonical_item.quantity, 3)
        self.assertIs(canonical_item.operator_requested, True)
        self.assertIs(canonical_item.returned, False)
        self.assertFalse(ReservationItem.objects.filter(pk=duplicate_item.pk).exists())
        self.assertEqual(
            ReservationItem.objects.filter(reservation=reservation, equipment=canonical).count(),
            1,
        )
        reservation.refresh_from_db()
        fee.refresh_from_db()
        self.assertEqual(reservation.estimated_total, Decimal("6500.00"))
        self.assertEqual(fee.unit_price, Decimal("1000.00"))
        self.assertEqual(fee.subtotal, Decimal("1000.00"))

        # Re-running against the same duplicate source is harmless.
        migration.merge_reservation_items(
            ReservationItem,
            duplicate_equipment_id=duplicate.pk,
            canonical_equipment_id=canonical.pk,
            db="default",
        )
        canonical_item.refresh_from_db()
        self.assertEqual(canonical_item.quantity, 3)
