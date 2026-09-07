from django.db import models


class Facility(models.Model):
    class FacilityType(models.TextChoices):
        GYMNASIUM = "GYMNASIUM", "Gymnasium"
        CAFETERIA = "CAFETERIA", "Cafeteria"
        AVR = "AVR", "Audio-Visual Room"
        MULTI_PURPOSE = "MULTI_PURPOSE", "Multi-Purpose Hall"
        OUTDOOR = "OUTDOOR", "Outdoor Area"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        OPERATIONAL = "OPERATIONAL", "Operational"
        MAINTENANCE = "MAINTENANCE", "Under Maintenance"

    name = models.CharField(max_length=120, unique=True)
    facility_type = models.CharField(
        max_length=32, choices=FacilityType.choices, default=FacilityType.OTHER
    )
    description = models.TextField(blank=True)
    capacity = models.PositiveIntegerField(default=0)
    location = models.CharField(max_length=160, blank=True)
    image = models.ImageField(upload_to="facilities/", blank=True, null=True)
    rules = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=32, choices=Status.choices, default=Status.OPERATIONAL
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class OperatingHour(models.Model):
    class Day(models.IntegerChoices):
        MONDAY = 0, "Monday"
        TUESDAY = 1, "Tuesday"
        WEDNESDAY = 2, "Wednesday"
        THURSDAY = 3, "Thursday"
        FRIDAY = 4, "Friday"
        SATURDAY = 5, "Saturday"
        SUNDAY = 6, "Sunday"

    facility = models.ForeignKey(
        Facility, on_delete=models.CASCADE, related_name="operating_hours"
    )
    day_of_week = models.PositiveSmallIntegerField(choices=Day.choices)
    open_time = models.TimeField(null=True, blank=True)  # None -> closed
    close_time = models.TimeField(null=True, blank=True)

    class Meta:
        ordering = ["day_of_week"]
        constraints = [
            models.UniqueConstraint(
                fields=["facility", "day_of_week"], name="unique_facility_day"
            )
        ]

    @property
    def is_closed(self) -> bool:
        return self.open_time is None or self.close_time is None

    def __str__(self) -> str:
        label = FacilityOperatingHours.day_label(self.day_of_week)
        if self.is_closed:
            return f"{label}: Closed"
        return f"{label}: {self.open_time:%H:%M} - {self.close_time:%H:%M}"


class FacilityOperatingHours:
    """Small helper for day labels shared by serializers."""

    DAY_LABELS = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]

    @staticmethod
    def day_label(day_of_week: int) -> str:
        return FacilityOperatingHours.DAY_LABELS[day_of_week]