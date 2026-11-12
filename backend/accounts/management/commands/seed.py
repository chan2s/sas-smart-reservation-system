"""Seed the database with institutional reference data.

Reference data (users, facilities, operating hours, equipment categories and
inventory) is always created. Real reservation data comes from the system's
users; ``--with-demo-reservations`` adds a small set of clearly-labelled demo
records that are useful only for previewing the UI.
"""

import random
from datetime import date, time, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Organization
from equipment.models import (
    Equipment,
    EquipmentCategory,
    FacilityResource,
    MaintenanceRecord,
)
from facilities.models import Facility, OperatingHour
from reservations.models import (
    PricingRule,
    Reservation,
    ReservationEvent,
    ReservationItem,
)

User = get_user_model()

FACILITIES = [
    {
        "name": "Gymnasium",
        "facility_type": Facility.FacilityType.GYMNASIUM,
        "description": (
            "A full-sized indoor court with bleacher seating, suited for "
            "athletic events, assemblies, and large gatherings. The floor is "
            "polished wood — rubber-soled footwear only."
        ),
        "capacity": 2000,
        "location": "Main Building, Ground Floor",
        # Open court floor: the space itself provides no seating, so chairs are
        # suggested per participant. "bleachers" is informational only — it does
        # not suppress any suggestion (spectators sit there during sports).
        "seating_type": Facility.SeatingType.OPEN_FLOOR,
        "built_in_seats": None,
        "built_ins": ["bleachers"],
        "rules": [
            "Rubber-soled shoes only on the court floor",
            "Food and drinks are not allowed on the court area",
            "No confetti or glitter",
            "All equipment must be returned to storage after use",
        ],
    },
    {
        "name": "Dorm Cafeteria",
        "facility_type": Facility.FacilityType.CAFETERIA,
        "description": (
            "The campus cafeteria serves as an open event space during "
            "non-dining hours. Ideal for receptions, bazaars, and social "
            "gatherings with flexible table arrangements."
        ),
        "capacity": 500,
        "location": "Student Center, Ground Floor",
        # A dining space: it already seats 300 at its own tables and chairs, so
        # extra seating is only suggested above that.
        "seating_type": Facility.SeatingType.TABLES_AND_CHAIRS,
        "built_in_seats": 300,
        "built_ins": ["tables", "chairs"],
        "rules": [
            "Outside catering requires prior coordination with SAS",
            "Tables and chairs must be rearranged back to default layout",
            "Waste segregation is strictly enforced",
        ],
    },
]

EQUIPMENT = [
    ("LED Wall", "monitor", [{"name": "LED Wall", "total": 1, "location": "", "unit": "unit", "asset_code": ""}]),
    ("Sound System", "volume-2", [{"name": "Sound System", "total": 6, "location": "", "unit": "set", "asset_code": ""}]),
    ("Plastic Chairs", "armchair", [{"name": "Plastic Chairs", "total": 300, "location": "", "unit": "piece", "asset_code": ""}]),
]


class Command(BaseCommand):
    help = "Seed reference data and optionally demo reservations."

    def add_arguments(self, parser):
        parser.add_argument(
            "--with-demo-reservations",
            action="store_true",
            help="Also create a small set of clearly-labelled demo reservations for UI preview.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        self.seed_organizations()
        self.seed_users()
        self.seed_facilities()
        self.seed_equipment()
        self.seed_facility_resources()
        self.seed_pricing()
        if options["with_demo_reservations"]:
            self.seed_demo_reservations()
        self.stdout.write(self.style.SUCCESS("Seed complete."))

    # ------------------------------------------------------------------

    def seed_organizations(self):
        """The nine managed internal organizations (idempotent).

        Mirrors the data migration so a fresh ``manage.py seed`` deployment
        gets the same managed list. Keyed by acronym/organization_code, so it
        never duplicates and never clobbers staff edits.
        """
        for acronym, name in Organization.INTERNAL_ORGANIZATIONS:
            organization, created = Organization.objects.get_or_create(
                organization_code=acronym,
                defaults={
                    "acronym": acronym,
                    "organization_name": name,
                    "organization_type": Organization.OrganizationType.INTERNAL,
                    "verification_status": Organization.VerificationStatus.APPROVED,
                    "is_active": True,
                    "contact_person": name,
                    "contact_email": "",
                },
            )
            if created:
                self.stdout.write(f"  + Organization: {acronym} — {name}")
            elif not organization.acronym:
                organization.acronym = acronym
                organization.save(update_fields=["acronym"])

    def seed_users(self):
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser(
                username="admin",
                email="admin@school.edu",
                password="admin1234",
                first_name="SAS",
                last_name="Administrator",
                role=User.Role.ADMIN,
                organization="SAS Office",
            )
            self.stdout.write("  + admin (Administrator)")
        if not User.objects.filter(username="staff").exists():
            User.objects.create_user(
                username="staff",
                email="staff@school.edu",
                password="staff1234",
                first_name="SAS",
                last_name="Staff",
                role=User.Role.STAFF,
                organization="SAS Office",
            )
            self.stdout.write("  + staff (SAS Staff)")
        if not User.objects.filter(username="requester").exists():
            User.objects.create_user(
                username="requester",
                email="requester@school.edu",
                password="requester1234",
                first_name="Sample",
                last_name="Requester",
                role=User.Role.REQUESTER,
                organization="Student Affairs",
            )
            self.stdout.write("  + requester (Requester)")

    def seed_facilities(self):
        Facility.objects.exclude(name__in=[row["name"] for row in FACILITIES]).update(is_active=False)
        for index, data in enumerate(FACILITIES):
            facility, created = Facility.objects.get_or_create(
                name=data["name"],
                defaults={
                    "facility_type": data["facility_type"],
                    "description": data["description"],
                    "capacity": data["capacity"],
                    "location": data["location"],
                    "rules": data["rules"],
                    "seating_type": data.get("seating_type"),
                    "built_in_seats": data.get("built_in_seats"),
                    "built_ins": data.get("built_ins", []),
                },
            )
            if not facility.is_active:
                facility.is_active = True
                facility.save(update_fields=["is_active", "updated_at"])
            if created:
                self.stdout.write(f"  + Facility: {facility.name}")
            elif self._backfill_seating_metadata(facility, data):
                self.stdout.write(f"  ~ Facility seating metadata: {facility.name}")
            for day in range(7):
                OperatingHour.objects.get_or_create(
                    facility=facility,
                    day_of_week=day,
                    defaults={
                        "open_time": time(6, 0),
                        "close_time": time(22, 0) if day < 5 else time(18, 0),
                    },
                )

    def _backfill_seating_metadata(self, facility, data):
        """Fill in seating metadata on an existing facility row.

        Only ever fills a value that is still unset, so re-running the seed
        cannot overwrite an administrator's own seating details. Returns True
        when something changed.
        """
        fields = []
        if facility.seating_type is None and data.get("seating_type"):
            facility.seating_type = data["seating_type"]
            fields.append("seating_type")
        if facility.built_in_seats is None and data.get("built_in_seats") is not None:
            facility.built_in_seats = data["built_in_seats"]
            fields.append("built_in_seats")
        if not facility.built_ins and data.get("built_ins"):
            facility.built_ins = data["built_ins"]
            fields.append("built_ins")
        if not fields:
            return False
        facility.save(update_fields=[*fields, "updated_at"])
        return True

    def seed_equipment(self):
        Equipment.objects.update(is_active=False)
        EquipmentCategory.objects.update(is_active=False)
        for category_name, icon, items in EQUIPMENT:
            category, created = EquipmentCategory.objects.get_or_create(
                name=category_name, defaults={"icon": icon}
            )
            category.is_active = True
            category.save(update_fields=["is_active"])
            if created:
                self.stdout.write(f"  + Category: {category_name}")
            for item in items:
                eq, created = Equipment.objects.get_or_create(
                    name=item["name"],
                    defaults={
                        "category": category,
                        "total_quantity": item["total"],
                        "storage_location": item["location"],
                        "unit": item.get("unit", "unit"),
                        "asset_code": item.get("asset_code", ""),
                    },
                )
                if not eq.is_active:
                    eq.is_active = True
                    eq.save(update_fields=["is_active"])
                if eq.total_quantity == 0 and item["total"] > 0:
                    eq.total_quantity = item["total"]
                    eq.save(update_fields=["total_quantity", "updated_at"])
                if created:
                    self.stdout.write(f"    + {eq.name} ({eq.total_quantity})")

    def seed_facility_resources(self):
        """Expose the same official equipment catalog at both official spaces."""
        for facility in Facility.objects.filter(name__in=["Gymnasium", "Dorm Cafeteria"], is_active=True):
            for equipment in Equipment.objects.filter(is_active=True):
                FacilityResource.objects.update_or_create(
                    facility=facility,
                    equipment=equipment,
                    defaults={
                        "is_active": True,
                        "additional_fee": "0.00",
                        "operator_available": False,
                        "operator_required": False,
                        "operator_fee": "0.00",
                    },
                )

    def seed_pricing(self):
        """Seed the single official rate configuration."""
        PricingRule.objects.all().update(is_active=False)
        facilities = (
            (Facility.FacilityType.GYMNASIUM, "Gymnasium"),
            (Facility.FacilityType.CAFETERIA, "Dorm Cafeteria"),
        )
        periods = (
            ("WHOLE_DAY", "5000.00", PricingRule.Unit.FLAT),
            ("HALF_DAY", "2500.00", PricingRule.Unit.FLAT),
            ("PER_HOUR", "650.00", PricingRule.Unit.HOUR),
        )
        for facility_type, label in facilities:
            for period, price, unit in periods:
                PricingRule.objects.update_or_create(
                    fee_type=PricingRule.FeeType.FACILITY,
                    facility_type=facility_type,
                    equipment_category=None,
                    rental_period=period,
                    defaults={
                        "label": label,
                        "unit": unit,
                        "unit_price": price,
                        "included_hours": 0,
                        "is_active": True,
                    },
                )
        rates = (
            ("LED Wall", "WHOLE_DAY", "15000.00", PricingRule.Unit.FLAT, PricingRule.FeeType.EQUIPMENT),
            ("LED Wall", "HALF_DAY", "7500.00", PricingRule.Unit.FLAT, PricingRule.FeeType.EQUIPMENT),
            ("Sound System", "", "1000.00", PricingRule.Unit.UNIT, PricingRule.FeeType.EQUIPMENT),
            ("Plastic Chairs", "", "5.00", PricingRule.Unit.UNIT, PricingRule.FeeType.EQUIPMENT),
            ("LED Wall", "", "500.00", PricingRule.Unit.FLAT, PricingRule.FeeType.OPERATOR),
            ("Sound System", "", "500.00", PricingRule.Unit.FLAT, PricingRule.FeeType.OPERATOR),
        )
        for name, period, price, unit, fee_type in rates:
            category = EquipmentCategory.objects.get(name=name)
            PricingRule.objects.update_or_create(
                fee_type=fee_type,
                facility_type="",
                equipment_category=category,
                rental_period=period,
                defaults={
                    "label": f"{name} Operator" if fee_type == PricingRule.FeeType.OPERATOR else name,
                    "unit": unit,
                    "unit_price": price,
                    "is_active": True,
                },
            )
        PricingRule.objects.update_or_create(
            fee_type=PricingRule.FeeType.ENVIRONMENTAL,
            facility_type="",
            equipment_category=None,
            rental_period="",
            defaults={
                "label": "Environmental Fee",
                "unit": PricingRule.Unit.FLAT,
                "unit_price": "500.00",
                "is_active": True,
            },
        )

    def seed_demo_reservations(self):
        """Clearly-labelled demo records for UI preview only."""
        requester = User.objects.get(username="requester")
        staff = User.objects.get(username="staff")
        gym = Facility.objects.get(name="Gymnasium")
        cafeteria = Facility.objects.get(name="Dorm Cafeteria")
        plastic_chairs = Equipment.objects.get(name="Plastic Chairs")
        led_wall = Equipment.objects.get(name="LED Wall")
        sound = Equipment.objects.get(name="Sound System")

        today = date.today()
        # The first pending demo reservation is created for "today" so the
        # dashboard preview shows live content without hardcoding dates.
        demo = [
            {
                "event_name": "[DEMO] Intramurals Opening",
                "facility": gym,
                "date": today,
                "start": time(8, 0),
                "end": time(12, 0),
                "status": Reservation.Status.PENDING,
                "event_type": Reservation.EventType.SPORTS,
                "items": [(plastic_chairs, 100)],
                "participants": 500,
            },
            {
                "event_name": "[DEMO] Accreditation Workshop",
                "facility": gym,
                "date": today + timedelta(days=1),
                "start": time(9, 0),
                "end": time(17, 0),
                "status": Reservation.Status.APPROVED,
                "event_type": Reservation.EventType.ACADEMIC,
                "items": [(led_wall, 1), (sound, 1)],
                "participants": 80,
            },
            {
                "event_name": "[DEMO] Alumni Homecoming Reception",
                "facility": cafeteria,
                "date": today + timedelta(days=3),
                "start": time(16, 0),
                "end": time(20, 0),
                "status": Reservation.Status.APPROVED,
                "event_type": Reservation.EventType.CULTURAL,
                "items": [(plastic_chairs, 150)],
                "participants": 300,
            },
        ]

        for index, data in enumerate(demo):
            if Reservation.objects.filter(event_name=data["event_name"]).exists():
                continue
            reservation = Reservation.objects.create(
                requester=requester,
                organization="Student Affairs",
                event_name=data["event_name"],
                facility=data["facility"],
                date=data["date"],
                start_time=data["start"],
                end_time=data["end"],
                status=data["status"],
                event_type=data["event_type"],
                expected_participants=data["participants"],
                purpose="Demo record for previewing the interface.",
            )
            for equipment, quantity in data["items"]:
                ReservationItem.objects.create(
                    reservation=reservation, equipment=equipment, quantity=quantity
                )
            ReservationEvent.objects.create(
                reservation=reservation,
                actor=requester,
                event_type=ReservationEvent.EventType.CREATED,
                message="Reservation submitted for approval.",
            )
            if data["status"] == Reservation.Status.APPROVED:
                ReservationEvent.objects.create(
                    reservation=reservation,
                    actor=staff,
                    event_type=ReservationEvent.EventType.APPROVED,
                    from_status=Reservation.Status.PENDING,
                    to_status=Reservation.Status.APPROVED,
                    message="Approved.",
                )
            self.stdout.write(f"  + Demo reservation: {reservation.reservation_id}")
