import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class RecommendationRule(models.Model):
    """A DB-editable override for the recommendation engine's built-in rules.

    Each row redefines how one equipment category is recommended for a slice
    of events. Which row "wins" for an event is decided by specificity:

    1. Rules scoped to the event's exact type beat generic ones.
    2. Then rules scoped to the facility's exact type.
    3. Then rules with a participant range containing the headcount.
    4. Then higher priority (lower number).
    5. Then the most recently updated row.

    Calculation types:

    * ``FIXED``               — always ``quantity_value`` units.
    * ``PER_PARTICIPANT``     — ``participants * quantity_value``.
    * ``PER_GROUP``           — ``ceil(participants / participants_per_unit)``
      with a minimum of one unit.
    * ``THRESHOLD``           — tiered lookup on participants:
      ``<= t1 -> q1; <= t2 -> q2; else -> q3`` (empty tier -> quantity_value).

    When no active rule matches an event, the engine falls back to its
    built-in category rules, so a fresh deployment behaves exactly like the
    pre-model engine until staff add overrides.
    """

    class CalculationType(models.TextChoices):
        FIXED = "FIXED", "Fixed quantity"
        PER_PARTICIPANT = "PER_PARTICIPANT", "Units per participant"
        PER_GROUP = "PER_GROUP", "Units per group of participants"
        THRESHOLD = "THRESHOLD", "Threshold tiers"

    category = models.ForeignKey(
        "equipment.EquipmentCategory",
        on_delete=models.CASCADE,
        related_name="recommendation_rules",
        help_text="Equipment category this rule recommends.",
    )
    event_type = models.CharField(
        max_length=32,
        blank=True,
        help_text="Leave blank to apply to all event types.",
    )
    facility_type = models.CharField(
        max_length=32,
        blank=True,
        help_text="Leave blank to apply to all facility types.",
    )
    min_participants = models.PositiveIntegerField(
        default=0,
        blank=True,
        help_text="Rule applies when participants >= this value. Leave empty for no minimum.",
    )
    max_participants = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Rule applies when participants <= this value. Blank = no upper limit.",
    )
    calculation_type = models.CharField(
        max_length=20,
        choices=CalculationType.choices,
        default=CalculationType.PER_GROUP,
    )
    quantity_value = models.PositiveIntegerField(
        default=1,
        help_text=(
            "Meaning depends on the calculation type: fixed quantity, "
            "multiplier per participant, or units per group."
        ),
    )
    participants_per_unit = models.PositiveIntegerField(
        default=10,
        help_text="For 'units per group': one unit covers this many participants (ceiling division).",
    )
    threshold_tier_1 = models.PositiveIntegerField(null=True, blank=True, help_text="Threshold tiers: participants <= tier 1 → tier 1 quantity.")
    threshold_quantity_1 = models.PositiveIntegerField(null=True, blank=True)
    threshold_tier_2 = models.PositiveIntegerField(null=True, blank=True, help_text="Threshold tiers: participants <= tier 2 → tier 2 quantity.")
    threshold_quantity_2 = models.PositiveIntegerField(null=True, blank=True)
    threshold_quantity_3 = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Threshold tiers: quantity when participants exceed tier 2. Blank = use 'Fixed quantity' value.",
    )
    priority = models.IntegerField(
        default=100,
        help_text="Tie-breaker when several rules match: lower number wins.",
    )
    explanation = models.CharField(
        max_length=200,
        blank=True,
        help_text=(
            "Custom reason shown to requesters, e.g. '1 table per 10 "
            "participants, rounded up'. Leave blank to auto-generate one."
        ),
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["priority", "id"]
        indexes = [
            models.Index(fields=["event_type", "facility_type"]),
            models.Index(fields=["is_active"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=~models.Q(min_participants__lt=0),
                name="recommendation_rule_min_participants_nonnegative",
            ),
            models.CheckConstraint(
                check=models.Q(
                    models.Q(max_participants__isnull=True)
                    | models.Q(max_participants__gte=models.F("min_participants"))
                ),
                name="recommendation_rule_participant_range_valid",
            ),
            models.CheckConstraint(
                check=models.Q(participants_per_unit__gte=1),
                name="recommendation_rule_group_size_positive",
            ),
        ]

    def __str__(self) -> str:
        scope = self.event_type or "All events"
        if self.facility_type:
            scope += f" · {self.get_facility_type_display()}"
        return f"{scope}: {self.get_calculation_type_display()} for {self.category.name}"


class Reservation(models.Model):
    class RequesterType(models.TextChoices):
        """Who the reservation is FOR — independent of who created it."""

        CAMPUS = "CAMPUS", "Campus User"
        EXTERNAL = "EXTERNAL", "External Organization"

    class OrganizationType(models.TextChoices):
        SCHOOL = "SCHOOL", "School"
        GOVERNMENT = "GOVERNMENT", "Government Organization"
        PRIVATE = "PRIVATE", "Private Organization"
        COMMUNITY = "COMMUNITY", "Community Organization"
        SPORTS = "SPORTS", "Sports Organization"
        COMPANY = "COMPANY", "Company"
        INDIVIDUAL = "INDIVIDUAL", "Individual"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        ACTIVE = "ACTIVE", "Active"
        COMPLETED = "COMPLETED", "Completed"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled"

    class EventType(models.TextChoices):
        SEMINAR = "SEMINAR", "Seminar"
        MEETING = "MEETING", "Meeting"
        WORKSHOP = "WORKSHOP", "Workshop"
        TRAINING = "TRAINING", "Training"
        SPORTS = "SPORTS", "Sports Event"
        CONFERENCE = "CONFERENCE", "Conference"
        RECOGNITION = "RECOGNITION", "Recognition Program"
        ORIENTATION = "ORIENTATION", "Orientation"
        CULTURAL = "CULTURAL", "Cultural Event"
        ACADEMIC = "ACADEMIC", "Academic Event"
        OTHER = "OTHER", "Other"

    # Statuses that hold resources and block availability.
    ACTIVE_STATUSES = [Status.PENDING, Status.APPROVED, Status.ACTIVE]

    reservation_id = models.CharField(max_length=20, unique=True, editable=False)
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reservations",
        null=True,
        blank=True,
        help_text=(
            "Account of the requester. Null for external requesters who do "
            "not have accounts."
        ),
    )
    requester_type = models.CharField(
        max_length=16,
        choices=RequesterType.choices,
        default=RequesterType.CAMPUS,
        db_index=True,
    )
    organization = models.CharField(max_length=120, blank=True)
    organization_type = models.CharField(
        max_length=32,
        choices=OrganizationType.choices,
        blank=True,
        help_text="For external requesters: what kind of organization they are.",
    )
    contact_email = models.EmailField(
        blank=True,
        help_text=(
            "For external requesters, this doubles as the tracking "
            "verification field (reservation code + email)."
        ),
    )
    # Who entered the reservation into the system — kept separate from the
    # requester because administrators create reservations on behalf of
    # other people/organizations.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reservations_created",
        help_text="Account that entered the reservation into the system.",
    )
    event_name = models.CharField(max_length=160)
    event_type = models.CharField(
        max_length=32, choices=EventType.choices, default=EventType.OTHER
    )
    description = models.TextField(blank=True)
    purpose = models.CharField(max_length=200, blank=True)
    expected_participants = models.PositiveIntegerField(default=0)
    contact_person = models.CharField(max_length=120, blank=True)
    special_requirements = models.TextField(blank=True)

    facility = models.ForeignKey(
        "facilities.Facility", on_delete=models.PROTECT, related_name="reservations"
    )
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()

    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reservations_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    checkin_code = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    checked_out_at = models.DateTimeField(null=True, blank=True)
    early_check_in_override = models.BooleanField(
        default=False,
        help_text="True when an administrator checked the reservation in before the standard 3-hour window.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["date", "status"]),
            models.Index(fields=["facility", "date"]),
            models.Index(fields=["requester_type", "status"]),
            models.Index(fields=["contact_email"]),
        ]

    def save(self, *args, **kwargs):
        if not self.reservation_id:
            self.reservation_id = self._next_reservation_id()
        super().save(*args, **kwargs)

    def _next_reservation_id(self) -> str:
        year = self.date.year if self.date else None
        prefix = f"SAS-{year}" if year else "SAS"
        last = (
            Reservation.objects.filter(reservation_id__startswith=prefix)
            .order_by("-reservation_id")
            .values_list("reservation_id", flat=True)
            .first()
        )
        if last:
            try:
                seq = int(last.rsplit("-", 1)[1]) + 1
            except (IndexError, ValueError):
                seq = 1
        else:
            seq = 1
        return f"{prefix}-{seq:05d}"

    @property
    def requester_display_name(self) -> str:
        """Human name of the requester, account or external alike."""
        if self.requester_type == self.RequesterType.EXTERNAL:
            return self.organization or self.contact_person or "External Requester"
        return self.requester.display_name if self.requester else "—"

    @property
    def requester_type_label(self) -> str:
        return self.get_requester_type_display()

    @property
    def is_today(self) -> bool:
        from datetime import date

        return self.date == date.today()

    @property
    def start_datetime(self):
        """Timezone-aware start of the event (date + start_time)."""
        return timezone.make_aware(datetime.combine(self.date, self.start_time))

    @property
    def check_in_open_time(self):
        """Check-in window opens 3 hours before the event start."""
        return self.start_datetime - timedelta(hours=3)

    def __str__(self) -> str:
        return f"{self.reservation_id} — {self.event_name}"


class ReservationItem(models.Model):
    reservation = models.ForeignKey(
        Reservation, on_delete=models.CASCADE, related_name="items"
    )
    equipment = models.ForeignKey(
        "equipment.Equipment", on_delete=models.PROTECT, related_name="reservation_items"
    )
    quantity = models.PositiveIntegerField(default=1)
    returned = models.BooleanField(default=False)

    class Meta:
        ordering = ["equipment__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["reservation", "equipment"], name="unique_reservation_equipment"
            )
        ]

    def __str__(self) -> str:
        return f"{self.quantity}× {self.equipment.name}"


class ReservationEvent(models.Model):
    class EventType(models.TextChoices):
        CREATED = "CREATED", "Created"
        SUBMITTED = "SUBMITTED", "Submitted"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        CHANGES_REQUESTED = "CHANGES_REQUESTED", "Changes requested"
        CANCELLED = "CANCELLED", "Cancelled"
        CHECKED_IN = "CHECKED_IN", "Checked in"
        CHECKED_OUT = "CHECKED_OUT", "Checked out"
        COMMENT = "COMMENT", "Comment"

    reservation = models.ForeignKey(
        Reservation, on_delete=models.CASCADE, related_name="events"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reservation_events",
    )
    event_type = models.CharField(max_length=32, choices=EventType.choices)
    from_status = models.CharField(
        max_length=16, blank=True, choices=Reservation.Status.choices
    )
    to_status = models.CharField(max_length=16, blank=True, choices=Reservation.Status.choices)
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.reservation.reservation_id} — {self.event_type}"


class InspectionReport(models.Model):
    class FacilityCondition(models.TextChoices):
        EXCELLENT = "EXCELLENT", "Excellent"
        GOOD = "GOOD", "Good"
        FAIR = "FAIR", "Fair"
        POOR = "POOR", "Poor"
        DAMAGED = "DAMAGED", "Damaged"

    reservation = models.OneToOneField(
        Reservation, on_delete=models.CASCADE, related_name="inspection"
    )
    facility_condition = models.CharField(
        max_length=16, choices=FacilityCondition.choices, default=FacilityCondition.GOOD
    )
    equipment_returned = models.BooleanField(default=False)
    missing_items = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    photo = models.ImageField(upload_to="inspections/", blank=True, null=True)
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="inspection_reports",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Inspection — {self.reservation.reservation_id}"