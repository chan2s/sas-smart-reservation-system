from decimal import Decimal
from django.utils import timezone

from django.conf import settings
from django.db import models


class EquipmentCategory(models.Model):
    name = models.CharField(max_length=80, unique=True)
    icon = models.CharField(max_length=40, blank=True)  # lucide icon key used by the frontend
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "equipment categories"

    def __str__(self) -> str:
        return self.name


class Equipment(models.Model):
    class Condition(models.TextChoices):
        EXCELLENT = "EXCELLENT", "Excellent"
        GOOD = "GOOD", "Good"
        FAIR = "FAIR", "Fair"
        POOR = "POOR", "Poor"
        DAMAGED = "DAMAGED", "Damaged"

    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        MAINTENANCE = "MAINTENANCE", "Under Maintenance"
        UNAVAILABLE = "UNAVAILABLE", "Unavailable"
        RETIRED = "RETIRED", "Retired"

    class Unit(models.TextChoices):
        """Counting unit shown with quantities ("112 pieces × ₱5.00")."""

        UNIT = "unit", "Unit"
        PIECE = "piece", "Piece"
        SET = "set", "Set"
        PAIR = "pair", "Pair"
        BOX = "box", "Box"
        PACKAGE = "package", "Package"

    class PricingMethod(models.TextChoices):
        """How this equipment is priced."""
        PER_UNIT = "PER_UNIT", "Per Unit (Quantity-Based)"
        DURATION = "DURATION", "Half-Day / Whole-Day"
        PACKAGE = "PACKAGE", "Package-Based (Not Individually Priced)"

    name = models.CharField(max_length=120)
    category = models.ForeignKey(
        EquipmentCategory, on_delete=models.PROTECT, related_name="items"
    )
    description = models.TextField(blank=True)
    total_quantity = models.PositiveIntegerField(default=1)
    #: Counting unit displayed with quantities. A controlled vocabulary
    #: (validated by the API); the default matches every pre-existing row.
    unit = models.CharField(
        max_length=40, choices=Unit.choices, default=Unit.UNIT
    )
    condition = models.CharField(
        max_length=16, choices=Condition.choices, default=Condition.GOOD
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.AVAILABLE
    )
    storage_location = models.CharField(max_length=120, blank=True)
    asset_code = models.CharField(max_length=60, blank=True)
    
    # Pricing Configuration
    pricing_method = models.CharField(
        max_length=16,
        choices=PricingMethod.choices,
        default=PricingMethod.PER_UNIT,
        help_text="How this equipment is priced: per unit, by duration (half/whole day), or package-based"
    )
    #: Per-unit price (used when pricing_method=PER_UNIT)
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Price per unit when using per-unit pricing (e.g., ₱5.00 per chair)"
    )
    #: Half-day price (used when pricing_method=DURATION)
    half_day_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Price for half-day (4+ hours) reservations when using duration-based pricing"
    )
    #: Whole-day price (used when pricing_method=DURATION)
    whole_day_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Price for whole-day (8+ hours) reservations when using duration-based pricing"
    )
    #: Hourly rate (used when pricing_method=DURATION for short reservations)
    hourly_rate = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Price per hour for reservations under 4 hours when using duration-based pricing"
    )
    #: Package price (used when pricing_method=PACKAGE). Charged once per
    #: package selected, so components bundled into the package are never
    #: charged individually. ``0`` means "not configured", letting the legacy
    #: per-category rate apply.
    package_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Price per package when using package-based pricing (e.g., Sound System Package)"
    )
    #: Flat operator/service fee for this item. ``0`` means the item has no
    #: operator fee. When set, reservation pricing charges it once per
    #: reservation (never per day or per bundled component) and only when the
    #: booking is on a weekend or ends after 5:00 PM on a weekday.
    operator_fee = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=(
            "Flat operator/service fee per reservation. Charged only for weekend "
            "bookings or weekday bookings ending after 5:00 PM."
        ),
    )
    
    #: Legacy per-item value retained for historical records. Current rental
    #: prices are managed through pricing_method and associated fields above.
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=(
            "Legacy item price retained for historical records. Use the new pricing "
            "configuration fields (unit_price, half_day_price, whole_day_price) instead."
        ),
    )
    image = models.ImageField(upload_to="equipment/", blank=True, null=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(unit_price__gte=0) & models.Q(half_day_price__gte=0) & 
                      models.Q(whole_day_price__gte=0) & models.Q(hourly_rate__gte=0) &
                      models.Q(package_price__gte=0),
                name="equipment_prices_nonnegative",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def get_effective_price_for_duration(self, duration_hours: Decimal) -> tuple[Decimal, str]:
        """Configured rate for a scheduled duration.

        Returns ``(price, unit)`` using the ``PricingRule.Unit`` vocabulary
        (``unit``, ``flat``, ``hour``). Delegates to the reservation pricing
        service, which is the single authoritative resolver, so a rate shown
        here is exactly the rate charged on a reservation.
        """
        from reservations.services.pricing import equipment_price_for

        return equipment_price_for(self, duration_hours)


class FacilityResource(models.Model):
    """One resource/equipment item assigned to ONE facility.

    This is the join between ``Facility`` and ``Equipment`` and the database
    source of truth for which resources a requester may pick. A piece of
    equipment may legitimately be assigned to several facilities (the same
    physical sound system can serve the Gymnasium and the AVR), so this is a
    through model rather than a field on ``Equipment``.

    The row also carries the facility-specific configuration staff manage in
    Django admin:

    * ``quantity`` — units of this resource available at this facility.
      ``0`` means "inherit the equipment's full inventory".
    * ``status`` — operational availability at this facility.
    * ``additional_fee`` — a per-unit fee for external organizations at this
      facility. A non-zero value overrides the global per-category
      ``PricingRule`` for this facility; ``0`` means "no override", so the
      configured category rate still applies. A resource is free only when
      neither is set.
    * ``operator_available`` / ``operator_required`` / ``operator_fee`` — the
      sound-system-operator style service. The fee is only charged when the
      requester opts in (or ``operator_required`` forces it), never merely
      because equipment is present.
    * ``is_recommendable`` and the ``recommendation_*`` fields — the criteria
      the booking form's "Suggested resources" list uses for this facility.
      Rules are per assignment, never global, so the same equipment can be
      recommended with different settings at different facilities.

    ``Equipment`` itself stays untouched; the resource's image comes from the
    existing equipment gallery, so the image feature is preserved.
    """

    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        UNAVAILABLE = "UNAVAILABLE", "Unavailable"
        MAINTENANCE = "MAINTENANCE", "Under Maintenance"
        DAMAGED = "DAMAGED", "Damaged"

    #: Statuses that keep the resource selectable in the reservation form.
    SELECTABLE_STATUSES = ("AVAILABLE",)

    facility = models.ForeignKey(
        "facilities.Facility",
        on_delete=models.CASCADE,
        related_name="facility_resources",
    )
    equipment = models.ForeignKey(
        Equipment,
        on_delete=models.CASCADE,
        related_name="facility_assignments",
    )
    quantity = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Units of this resource available at this facility. "
            "0 = inherit the equipment's total inventory."
        ),
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.AVAILABLE
    )
    additional_fee = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=(
            "Per-unit fee for external organizations at this facility. "
            "0 = use the configured per-category rate (no override)."
        ),
    )
    operator_available = models.BooleanField(
        default=False,
        help_text="Whether the requester may opt in to an operator/service for this resource.",
    )
    operator_required = models.BooleanField(
        default=False,
        help_text="When true the operator service fee is always charged for this resource.",
    )
    operator_fee = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Flat service fee for the operator, charged when selected/required.",
    )

    # --- Recommendation configuration -------------------------------------
    #
    # Everything the booking form's "Suggested resources" list may recommend
    # for this facility lives here, on the assignment itself. The engine has
    # no built-in equipment list: an item is recommended only when its
    # assignment opts in, is active/available, and the event matches these
    # criteria. The same equipment assigned to two facilities therefore has
    # independent recommendation settings.

    class RecommendationCalculation(models.TextChoices):
        FIXED = "FIXED", "Fixed quantity"
        PER_PARTICIPANT = "PER_PARTICIPANT", "Units per participant"
        PER_GROUP = "PER_GROUP", "Units per group of participants"
        THRESHOLD = "THRESHOLD", "Participant thresholds"

    is_recommendable = models.BooleanField(
        default=False,
        help_text=(
            "Offer this resource in the booking form's Suggested resources "
            "list when the criteria below match the event."
        ),
    )
    recommendation_event_types = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Event types this resource is recommended for, e.g. "
            '[\"SEMINAR\", \"CONFERENCE\"]. Leave empty for all event types.'
        ),
    )
    recommendation_calculation = models.CharField(
        max_length=20,
        choices=RecommendationCalculation.choices,
        default=RecommendationCalculation.PER_PARTICIPANT,
    )
    recommendation_quantity = models.PositiveIntegerField(
        default=1,
        help_text=(
            "Fixed quantity, multiplier per participant, or the quantity "
            "used above the highest threshold."
        ),
    )
    recommendation_participants_per_unit = models.PositiveIntegerField(
        default=10,
        help_text="For 'units per group': one unit covers this many participants.",
    )
    recommendation_min_participants = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Only recommend when participants are at least this many. Blank = no minimum.",
    )
    recommendation_max_participants = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Only recommend when participants are at most this many. Blank = no maximum.",
    )
    recommendation_min_quantity = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Never recommend fewer than this many units. Blank = no minimum.",
    )
    recommendation_max_quantity = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Never recommend more than this many units. Blank = no maximum.",
    )
    recommendation_tier_1 = models.PositiveIntegerField(
        null=True, blank=True, help_text="Threshold tiers: participants <= tier 1."
    )
    recommendation_tier_1_quantity = models.PositiveIntegerField(null=True, blank=True)
    recommendation_tier_2 = models.PositiveIntegerField(
        null=True, blank=True, help_text="Threshold tiers: participants <= tier 2."
    )
    recommendation_tier_2_quantity = models.PositiveIntegerField(null=True, blank=True)
    recommendation_tier_3 = models.PositiveIntegerField(
        null=True, blank=True, help_text="Threshold tiers: participants <= tier 3."
    )
    recommendation_tier_3_quantity = models.PositiveIntegerField(null=True, blank=True)
    recommendation_explanation = models.CharField(
        max_length=200,
        blank=True,
        help_text=(
            "Custom reason shown to requesters. Leave blank to generate one "
            "from the calculation above."
        ),
    )

    description = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_order", "equipment__name"]
        verbose_name = "facility resource"
        verbose_name_plural = "facility resources"
        constraints = [
            models.UniqueConstraint(
                fields=["facility", "equipment"],
                name="unique_facility_resource",
            )
        ]
        indexes = [models.Index(fields=["facility", "is_active"])]

    @property
    def effective_quantity(self) -> int:
        """Units available at this facility (falls back to the inventory total)."""
        if self.quantity:
            return self.quantity
        return self.equipment.total_quantity or 0

    def __str__(self) -> str:
        return f"{self.equipment.name} @ {self.facility.name}"


class EquipmentImage(models.Model):
    """One image in an equipment item's gallery.

    The gallery is the source of truth for image display. ``Equipment.image``
    is retained for backward compatibility with older records and API
    consumers; the serializer falls back to it whenever the gallery is empty.

    Ordering is always: primary image first, then ``display_order``, then the
    oldest image. None of this is stored on ``Equipment`` itself, so gallery
    changes never touch the equipment row.
    """

    equipment = models.ForeignKey(
        Equipment, on_delete=models.CASCADE, related_name="equipment_images"
    )
    image = models.ImageField(upload_to="equipment/")
    caption = models.CharField(max_length=160, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-is_primary", "display_order", "created_at", "id")

    def __str__(self) -> str:
        return f"{self.equipment.name} — image {self.pk or 'unsaved'}"


class MaintenanceRecord(models.Model):
    class IssueType(models.TextChoices):
        DAMAGE = "DAMAGE", "Damage"
        MISSING = "MISSING", "Missing item"
        MALFUNCTION = "MALFUNCTION", "Malfunction"
        MAINTENANCE = "MAINTENANCE", "Maintenance required"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        RESOLVED = "RESOLVED", "Resolved"

    equipment = models.ForeignKey(
        Equipment, on_delete=models.CASCADE, related_name="maintenance_records"
    )
    quantity = models.PositiveIntegerField(default=1)
    issue_type = models.CharField(max_length=16, choices=IssueType.choices)
    description = models.TextField(blank=True)
    photo = models.ImageField(upload_to="maintenance/", blank=True, null=True)
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="maintenance_reports"
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # A reporter may hold at most one OPEN report per piece of
            # equipment. Deliberately a PARTIAL constraint (only rows whose
            # status is OPEN): once a report is resolved it stops blocking, so
            # a fresh report can be filed for the same item. This is the
            # database-level backstop that makes concurrent submissions safe
            # on every backend, not just those with row-level locking.
            models.UniqueConstraint(
                fields=["equipment", "reported_by"],
                condition=models.Q(status="OPEN"),
                name="unique_open_report_per_equipment_reporter",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.equipment.name} — {self.get_issue_type_display()}"


class SoundSystemOperator(models.Model):
    """A qualified Sound System Operator available for rental reservations.
    
    Operators are managed independently from physical equipment inventory.
    Each operator has their own availability schedule and can be assigned to
    multiple reservations across different time slots.
    """
    
    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        UNAVAILABLE = "UNAVAILABLE", "Unavailable"
    
    name = models.CharField(max_length=120)
    contact_phone = models.CharField(max_length=20, blank=True)
    contact_email = models.EmailField(blank=True)
    rate = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("500.00"),
        help_text="Default operator rate per package/reservation"
    )
    status = models.CharField(
        max_length=16, 
        choices=Status.choices, 
        default=Status.AVAILABLE,
        help_text="Operational availability of this operator"
    )
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["name"]
    
    def __str__(self) -> str:
        return f"{self.name} ({self.get_status_display()})"


class EquipmentPackage(models.Model):
    """A bundle of equipment items treated as a single rentable package.
    
    Packages group multiple equipment items and optional required services
    (operators) into a single reservable unit. The package composition is
    configurable and inventory is calculated as the minimum availability
    across all required components.
    
    Currently used for Sound System Package implementation.
    """
    
    class Type(models.TextChoices):
        SOUND_SYSTEM = "SOUND_SYSTEM", "Sound System Package"
    
    package_type = models.CharField(
        max_length=32,
        choices=Type.choices,
        unique=True,
        help_text="Type/category of package"
    )
    name = models.CharField(max_length=120, help_text="Display name of the package")
    description = models.TextField(blank=True, help_text="Description of included items and services")
    operator_required = models.BooleanField(
        default=True,
        help_text="Whether an operator/technician is required for this package"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["package_type"]
    
    def __str__(self) -> str:
        return self.name


class EquipmentPackageComponent(models.Model):
    """A required component of an EquipmentPackage.
    
    Defines which equipment items and quantities are required to constitute
    one complete package unit. When availability is calculated, the package
    is only available if ALL components have sufficient quantities.
    """
    
    package = models.ForeignKey(
        EquipmentPackage,
        on_delete=models.CASCADE,
        related_name="components"
    )
    equipment = models.ForeignKey(
        Equipment,
        on_delete=models.CASCADE,
        related_name="package_components"
    )
    quantity_per_package = models.PositiveIntegerField(
        default=1,
        help_text="How many units of this equipment are required per complete package"
    )
    description = models.TextField(
        blank=True,
        help_text="Specific description of this component (e.g., '2x Wireless Microphones')"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = [["package", "equipment"]]
        ordering = ["equipment__name"]
    
    def __str__(self) -> str:
        return f"{self.package.name} → {self.quantity_per_package}× {self.equipment.name}"
