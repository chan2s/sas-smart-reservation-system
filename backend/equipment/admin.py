from django.contrib import admin

from .models import (
    Equipment,
    EquipmentCategory,
    EquipmentImage,
    FacilityResource,
    MaintenanceRecord,
)


@admin.register(EquipmentCategory)
class EquipmentCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "icon")


class EquipmentImageInline(admin.TabularInline):
    model = EquipmentImage
    extra = 0
    fields = ("image", "caption", "display_order", "is_primary")


class FacilityResourceInline(admin.TabularInline):
    """Assign an equipment item to facilities right from the item page."""

    model = FacilityResource
    extra = 0
    autocomplete_fields = ("facility",)
    fields = (
        "facility",
        "quantity",
        "status",
        "additional_fee",
        "operator_available",
        "operator_required",
        "operator_fee",
        "display_order",
        "is_active",
    )


@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "total_quantity", "condition", "is_active")
    list_filter = ("category", "condition", "is_active")
    search_fields = ("name",)
    inlines = (EquipmentImageInline, FacilityResourceInline)


@admin.register(FacilityResource)
class FacilityResourceAdmin(admin.ModelAdmin):
    """Manage which resources belong to which facility, without code changes.

    A resource/equipment item can be assigned to one or more facilities; each
    assignment carries the facility's own quantity, availability, additional
    fee, and operator/service configuration.
    """

    list_display = (
        "equipment",
        "facility",
        "quantity",
        "status",
        "additional_fee",
        "operator_available",
        "operator_fee",
        "is_active",
    )
    list_filter = ("facility", "status", "is_active", "operator_available")
    search_fields = ("equipment__name", "facility__name", "description")
    autocomplete_fields = ("equipment", "facility")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (
            "Resource",
            {
                "fields": ("equipment", "facility", "quantity", "status", "description"),
                "description": (
                    "Assign one equipment/resource item to one facility. "
                    "Quantity 0 inherits the equipment's total inventory. "
                    "Images come from the equipment item's gallery."
                ),
            },
        ),
        (
            "Fees",
            {
                "fields": ("additional_fee", "operator_available", "operator_required", "operator_fee"),
                "description": (
                    "Additional fee is per unit for external organizations at "
                    "this facility (0 = no additional fee). The operator is a "
                    "flat service charged only when requested, or always when required."
                ),
            },
        ),
        ("Display", {"fields": ("display_order", "notes", "is_active")}),
        ("Meta", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(MaintenanceRecord)
class MaintenanceRecordAdmin(admin.ModelAdmin):
    list_display = ("equipment", "quantity", "issue_type", "status", "created_at")
    list_filter = ("issue_type", "status")