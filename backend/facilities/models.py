from django.db import models


class Facility(models.Model):
    class FacilityType(models.TextChoices):
        GYMNASIUM = "GYMNASIUM", "Gymnasium"
        CAFETERIA = "CAFETERIA", "Cafeteria"
        AVR = "AVR", "Audio-Visual Room"
        MULTI_PURPOSE = "MULTI_PURPOSE", "Multi-Purpose Hall"
        OUTDOOR = "OUTDOOR", "Outdoor Area"
        OTHER = "OTHER", "Other"

    class SeatingType(models.TextChoices):
        """How the space is physically seated.

        Drives the reservation wizard's resource suggestions: a dining hall
        already has tables and chairs, so only the seating gap above its own
        seats should ever be suggested as extra equipment.
        """

        TABLES_AND_CHAIRS = "tables_and_chairs", "Tables and chairs"
        FIXED_ROWS = "fixed_rows", "Fixed rows"
        OPEN_FLOOR = "open_floor", "Open floor"

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
    # ---- Physical reality of the space (optional reference data) --------
    # All three fields are nullable/blank so every pre-existing facility keeps
    # working untouched: a null seating_type means "not verified yet", and the
    # wizard then asks the requester to choose seating themselves.
    seating_type = models.CharField(
        max_length=32,
        choices=SeatingType.choices,
        blank=True,
        null=True,
        default=None,
        help_text="How the space is seated. Leave empty when unverified.",
    )
    built_in_seats = models.PositiveIntegerField(
        blank=True,
        null=True,
        default=None,
        help_text=(
            "Seats the space already provides at tables/fixed rows. Leave "
            "empty when it has no fixed seating or is unverified."
        ),
    )
    built_ins = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            'Items the space already provides, e.g. '
            '["tables", "chairs", "projector", "sound_system", "stage", "podium"].'
        ),
    )
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


class FacilityImage(models.Model):
    """One image in a facility's gallery.

    The gallery is the source of truth for image display. ``Facility.image``
    is retained for backward compatibility with older records and API
    consumers; the serializer falls back to it whenever the gallery is empty.

    Ordering is always: primary image first, then ``order``, then the oldest
    image. None of this is stored on ``Facility`` itself, so gallery changes
    never touch the facility row.
    """

    facility = models.ForeignKey(
        Facility, on_delete=models.CASCADE, related_name="images"
    )
    image = models.ImageField(upload_to="facilities/")
    is_primary = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-is_primary", "order", "created_at", "id")

    def __str__(self) -> str:
        return f"{self.facility.name} — image {self.pk or 'unsaved'}"


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