from decimal import Decimal

from django.conf import settings
from django.db import models


class EquipmentCategory(models.Model):
    name = models.CharField(max_length=80, unique=True)
    icon = models.CharField(max_length=40, blank=True)  # lucide icon key used by the frontend
    description = models.TextField(blank=True)

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

    name = models.CharField(max_length=120)
    category = models.ForeignKey(
        EquipmentCategory, on_delete=models.PROTECT, related_name="items"
    )
    description = models.TextField(blank=True)
    total_quantity = models.PositiveIntegerField(default=1)
    unit = models.CharField(max_length=40, default="unit")
    condition = models.CharField(
        max_length=16, choices=Condition.choices, default=Condition.GOOD
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.AVAILABLE
    )
    storage_location = models.CharField(max_length=120, blank=True)
    asset_code = models.CharField(max_length=60, blank=True)
    image = models.ImageField(upload_to="equipment/", blank=True, null=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


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
      facility. When a row exists it is authoritative: ``0`` means explicitly
      "no additional fee" (so chairs/tables can be free) and the global
      per-category ``PricingRule`` is ignored.
    * ``operator_available`` / ``operator_required`` / ``operator_fee`` — the
      sound-system-operator style service. The fee is only charged when the
      requester opts in (or ``operator_required`` forces it), never merely
      because equipment is present.

    ``Equipment`` itself stays untouched; the resource's image comes from the
    existing equipment gallery, so the image feature is preserved.
    """

    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        UNAVAILABLE = "UNAVAILABLE", "Unavailable"
        MAINTENANCE = "MAINTENANCE", "Under Maintenance"

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
            "0 = no additional fee (this overrides any category rate)."
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

    def __str__(self) -> str:
        return f"{self.equipment.name} — {self.get_issue_type_display()}"