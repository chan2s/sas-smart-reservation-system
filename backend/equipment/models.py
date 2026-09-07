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