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

from equipment.models import Equipment, EquipmentCategory, MaintenanceRecord
from facilities.models import Facility, OperatingHour
from reservations.models import Reservation, ReservationEvent, ReservationItem

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
        "rules": [
            "Rubber-soled shoes only on the court floor",
            "Food and drinks are not allowed on the court area",
            "No confetti or glitter",
            "All equipment must be returned to storage after use",
        ],
    },
    {
        "name": "Cafeteria",
        "facility_type": Facility.FacilityType.CAFETERIA,
        "description": (
            "The campus cafeteria serves as an open event space during "
            "non-dining hours. Ideal for receptions, bazaars, and social "
            "gatherings with flexible table arrangements."
        ),
        "capacity": 500,
        "location": "Student Center, Ground Floor",
        "rules": [
            "Outside catering requires prior coordination with SAS",
            "Tables and chairs must be rearranged back to default layout",
            "Waste segregation is strictly enforced",
        ],
    },
    {
        "name": "Audio-Visual Room",
        "facility_type": Facility.FacilityType.AVR,
        "description": (
            "A fully equipped presentation room with a 4K projector, surround "
            "sound, and flexible seating. Ideal for seminars, workshops, and "
            "accreditation-related activities."
        ),
        "capacity": 120,
        "location": "Academic Building, 2nd Floor",
        "rules": [
            "Only SAS-trained operators may handle the projector system",
            "Keep the room dimmed when using the projector",
            "Report any equipment malfunction immediately",
        ],
    },
]

EQUIPMENT = [
    ("Sound Systems", "volume-2", [
        {"name": "Portable Sound System", "total": 4, "location": "SAS Equipment Room A", "unit": "set", "asset_code": "SAS-AUD-001"},
        {"name": "Stage Sound System", "total": 2, "location": "SAS Equipment Room A", "unit": "set", "asset_code": "SAS-AUD-002"},
    ]),
    ("Microphones", "mic", [
        {"name": "Wireless Microphone", "total": 8, "location": "SAS Equipment Room A", "unit": "unit", "asset_code": "SAS-MIC-001"},
        {"name": "Wired Microphone", "total": 6, "location": "SAS Equipment Room A", "unit": "unit", "asset_code": "SAS-MIC-002"},
    ]),
    ("Projectors", "projector", [
        {"name": "Portable Projector", "total": 3, "location": "SAS Equipment Room B", "unit": "unit", "asset_code": "SAS-PRJ-001"},
        {"name": "Projector Screen", "total": 4, "location": "SAS Equipment Room B", "unit": "unit", "asset_code": "SAS-PRJ-002"},
    ]),
    ("Tables", "table", [
        {"name": "Folding Table (6 ft)", "total": 40, "location": "SAS Storage", "unit": "unit", "asset_code": "SAS-FUR-001"},
        {"name": "Round Table", "total": 20, "location": "SAS Storage", "unit": "unit", "asset_code": "SAS-FUR-002"},
    ]),
    ("Chairs", "armchair", [
        {"name": "Folding Chair", "total": 200, "location": "SAS Storage", "unit": "unit", "asset_code": "SAS-FUR-003"},
        {"name": "Stackable Chair", "total": 100, "location": "SAS Storage", "unit": "unit", "asset_code": "SAS-FUR-004"},
    ]),
    ("Other Equipment", "package", [
        {"name": "Extension Cord (50 ft)", "total": 10, "location": "SAS Equipment Room B", "unit": "unit", "asset_code": "SAS-ELE-001"},
        {"name": "Event Signage Stand", "total": 6, "location": "SAS Storage", "unit": "unit", "asset_code": "SAS-OTH-001"},
    ]),
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
        self.seed_users()
        self.seed_facilities()
        self.seed_equipment()
        if options["with_demo_reservations"]:
            self.seed_demo_reservations()
        self.stdout.write(self.style.SUCCESS("Seed complete."))

    # ------------------------------------------------------------------

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
        for index, data in enumerate(FACILITIES):
            facility, created = Facility.objects.get_or_create(
                name=data["name"],
                defaults={
                    "facility_type": data["facility_type"],
                    "description": data["description"],
                    "capacity": data["capacity"],
                    "location": data["location"],
                    "rules": data["rules"],
                },
            )
            if created:
                self.stdout.write(f"  + Facility: {facility.name}")
            for day in range(7):
                OperatingHour.objects.get_or_create(
                    facility=facility,
                    day_of_week=day,
                    defaults={
                        "open_time": time(6, 0),
                        "close_time": time(22, 0) if day < 5 else time(18, 0),
                    },
                )

    def seed_equipment(self):
        for category_name, icon, items in EQUIPMENT:
            category, created = EquipmentCategory.objects.get_or_create(
                name=category_name, defaults={"icon": icon}
            )
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
                if created:
                    self.stdout.write(f"    + {eq.name} ({eq.total_quantity})")

    def seed_demo_reservations(self):
        """Clearly-labelled demo records for UI preview only."""
        requester = User.objects.get(username="requester")
        staff = User.objects.get(username="staff")
        gym = Facility.objects.get(name="Gymnasium")
        cafeteria = Facility.objects.get(name="Cafeteria")
        avr = Facility.objects.get(name="Audio-Visual Room")

        folding_chairs = Equipment.objects.get(name="Folding Chair")
        folding_tables = Equipment.objects.get(name="Folding Table (6 ft)")
        wireless_mics = Equipment.objects.get(name="Wireless Microphone")
        sound = Equipment.objects.get(name="Portable Sound System")

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
                "items": [(folding_chairs, 100), (folding_tables, 10), (wireless_mics, 2)],
                "participants": 500,
            },
            {
                "event_name": "[DEMO] Accreditation Workshop",
                "facility": avr,
                "date": today + timedelta(days=1),
                "start": time(9, 0),
                "end": time(17, 0),
                "status": Reservation.Status.APPROVED,
                "event_type": Reservation.EventType.ACADEMIC,
                "items": [(wireless_mics, 4), (sound, 1)],
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
                "items": [(folding_tables, 15), (folding_chairs, 150)],
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