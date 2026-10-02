from django.core.management.base import BaseCommand
from django.db import transaction
from datetime import time

from facilities.models import Facility, OperatingHour


FACILITIES = [
    {
        "name": "Gymnasium",
        "facility_type": Facility.FacilityType.GYMNASIUM,
        "description": (
            "A full-sized indoor court with bleacher seating, suited for "
            "athletic events, assemblies, and large gatherings. The floor "
            "is polished wood — rubber-soled footwear only."
        ),
        "capacity": 2000,
        "location": "Main Building, Ground Floor",
        "rules": [
            "Rubber-soled shoes only on the court floor",
            "Food and drinks are not allowed on the court area",
            "No confetti or glitter",
            "All equipment must be returned to storage after use",
        ],
        "seating_type": None,
        "built_in_seats": None,
        "built_ins": [],
        "status": Facility.Status.OPERATIONAL,
        "is_active": True,
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
        "seating_type": None,
        "built_in_seats": None,
        "built_ins": [],
        "status": Facility.Status.OPERATIONAL,
        "is_active": True,
    },
    {
        "name": "Audio-Visual Room",
        "facility_type": Facility.FacilityType.AVR,
        "description": (
            "A fully equipped presentation room with a 4K projector, "
            "surround sound, and flexible seating. Ideal for seminars, "
            "workshops, and accreditation-related activities."
        ),
        "capacity": 120,
        "location": "Academic Building, 2nd Floor",
        "rules": [
            "Only SAS-trained operators may handle the projector system",
            "Keep the room dimmed when using the projector",
            "Report any equipment malfunction immediately",
        ],
        "seating_type": None,
        "built_in_seats": None,
        "built_ins": [],
        "status": Facility.Status.OPERATIONAL,
        "is_active": True,
    },
    {
        "name": "Repro AVR",
        "facility_type": Facility.FacilityType.AVR,
        "description": "",
        "capacity": 50,
        "location": "",
        "rules": [],
        "seating_type": None,
        "built_in_seats": None,
        "built_ins": [],
        "status": Facility.Status.OPERATIONAL,
        "is_active": True,
    },
]


class Command(BaseCommand):
    help = "Create or update the default SAS RESERVE production facilities."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Seeding facilities...")

        facilities = {}

        for data in FACILITIES:
            name = data["name"]

            facility, created = Facility.objects.update_or_create(
                name=name,
                defaults=data,
            )

            facilities[name] = facility

            action = "Created" if created else "Updated"
            self.stdout.write(
                self.style.SUCCESS(
                    f"  {action}: {facility.name}"
                )
            )

        self.stdout.write("Seeding operating hours...")

        weekday_days = range(0, 5)
        weekend_days = range(5, 7)

        for facility in facilities.values():
            for day in weekday_days:
                OperatingHour.objects.update_or_create(
                    facility=facility,
                    day_of_week=day,
                    defaults={
                        "open_time": time(6, 0),
                        "close_time": time(22, 0),
                    },
                )

            for day in weekend_days:
                OperatingHour.objects.update_or_create(
                    facility=facility,
                    day_of_week=day,
                    defaults={
                        "open_time": time(6, 0),
                        "close_time": time(18, 0),
                    },
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully seeded {len(facilities)} facilities."
            )
        )