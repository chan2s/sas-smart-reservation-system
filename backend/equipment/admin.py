from django.contrib import admin
from django import forms
from django.core.exceptions import ValidationError

from .models import (
    Equipment,
    EquipmentCategory,
    EquipmentImage,
    EquipmentPackage,
    EquipmentPackageComponent,
    FacilityResource,
    MaintenanceRecord,
    SoundSystemOperator,
)


def _configured_builtin_description(facility) -> str:
    """Short description of the configured built-in amenities for one facility."""
    from equipment.services import configured_builtin_tokens_for_facility

    tokens = configured_builtin_tokens_for_facility(facility.id)
    if not tokens:
        return ""
    joined = ", ".join(tokens)
    if len(tokens) == 1:
        return f"Configured built-in amenity: {joined}."
    return f"Configured built-in amenities: {joined}."


class OfficialCategoryAdminForm(forms.ModelForm):
    class Meta:
        model = EquipmentCategory
        fields = "__all__"

    def clean(self):
        values = super().clean()
        if values.get("is_active", True) and (values.get("name") or "").strip().casefold() not in {
            "led wall", "sound system", "plastic chairs"
        }:
            raise ValidationError("Only LED Wall, Sound System, and Plastic Chairs are in the official catalog.")
        return values


class OfficialEquipmentAdminForm(forms.ModelForm):
    class Meta:
        model = Equipment
        fields = "__all__"

    def clean(self):
        values = super().clean()
        if values.get("is_active", True):
            name = (values.get("name") or "").strip()
            if name.casefold() not in {"led wall", "sound system", "plastic chairs"}:
                raise ValidationError("Only LED Wall, Sound System, and Plastic Chairs are in the official catalog.")
            category = values.get("category")
            if category is None or category.name.casefold() != name.casefold() or not category.is_active:
                raise ValidationError({"category": "Choose the matching active official equipment category."})
            duplicates = Equipment.objects.filter(name__iexact=name, is_active=True)
            if self.instance.pk:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                raise ValidationError({"name": "The unified catalog can have only one active item with this name."})
        return values


@admin.register(EquipmentCategory)
class EquipmentCategoryAdmin(admin.ModelAdmin):
    form = OfficialCategoryAdminForm
    list_display = ("name", "icon", "is_active")


class EquipmentImageInline(admin.TabularInline):
    model = EquipmentImage
    extra = 0
    fields = ("image", "caption", "display_order", "is_primary")


class FacilityResourceInline(admin.TabularInline):
    """Assign an equipment item to facilities right from the item page."""

    model = FacilityResource
    extra = 0
    readonly_fields = (
        "additional_fee",
        "operator_available",
        "operator_required",
        "operator_fee",
    )
    autocomplete_fields = ("facility",)
    fields = (
        "facility",
        "quantity",
        "status",
        "additional_fee",
        "operator_available",
        "operator_required",
        "operator_fee",
        "is_recommendable",
        "display_order",
        "is_active",
    )


@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    form = OfficialEquipmentAdminForm
    readonly_fields = ()  # No longer readonly - allow pricing configuration
    list_display = ("name", "category", "total_quantity", "pricing_method", "condition", "is_active")
    list_filter = ("category", "condition", "pricing_method", "is_active")
    search_fields = ("name",)
    inlines = (EquipmentImageInline, FacilityResourceInline)
    
    fieldsets = (
        (
            "Basic Information",
            {
                "fields": ("name", "category", "description", "total_quantity", "unit"),
            },
        ),
        (
            "Rental Pricing Configuration",
            {
                "fields": ("pricing_method", "operator_fee"),
                "description": "Choose how this equipment is priced: per unit (quantity-based), by rental duration (half-day/whole-day), or as part of a package. The operator fee is charged once per reservation on weekends or when a weekday booking ends after 5:00 PM.",
            },
        ),
        (
            "Per-Unit Pricing",
            {
                "fields": ("unit_price",),
                "description": "Configure when Pricing Method is 'Per Unit'. Price per unit (piece, set, etc.).",
                "classes": ("collapse",),
            },
        ),
        (
            "Duration-Based Pricing",
            {
                "fields": ("half_day_price", "whole_day_price", "hourly_rate"),
                "description": "Configure when Pricing Method is 'Half-Day / Whole-Day'. Prices for different reservation durations.",
                "classes": ("collapse",),
            },
        ),
        (
            "Package Pricing",
            {
                "fields": ("package_price",),
                "description": "Configure when Pricing Method is 'Package-Based'. Charged per package selected; bundled components are not charged individually.",
                "classes": ("collapse",),
            },
        ),
        (
            "Status & Location",
            {
                "fields": ("condition", "status", "storage_location", "asset_code", "is_active"),
            },
        ),
        (
            "Additional Information",
            {
                "fields": ("notes", "image"),
                "classes": ("collapse",),
            },
        ),
        (
            "Historical Data",
            {
                "fields": ("price",),
                "description": "Legacy per-item price retained for historical records. Use the new pricing fields above instead.",
                "classes": ("collapse",),
            },
        ),
    )


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
        "is_recommendable",
        "is_active",
    )
    list_filter = ("facility", "status", "is_active", "operator_available", "is_recommendable")
    search_fields = ("equipment__name", "facility__name", "description")
    autocomplete_fields = ("equipment", "facility")
    readonly_fields = (
        "additional_fee",
        "operator_available",
        "operator_required",
        "operator_fee",
        "created_at",
        "updated_at",
    )
    fieldsets = (
        (
            "Resource",
            {
                "fields": ("equipment", "facility", "quantity", "status", "description"),
                "description": _configured_builtin_description,
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
        (
            "Recommendation rules",
            {
                "fields": (
                    "is_recommendable",
                    "recommendation_event_types",
                    "recommendation_min_participants",
                    "recommendation_max_participants",
                    "recommendation_calculation",
                    "recommendation_quantity",
                    "recommendation_participants_per_unit",
                    "recommendation_tier_1",
                    "recommendation_tier_1_quantity",
                    "recommendation_tier_2",
                    "recommendation_tier_2_quantity",
                    "recommendation_tier_3",
                    "recommendation_tier_3_quantity",
                    "recommendation_min_quantity",
                    "recommendation_max_quantity",
                    "recommendation_explanation",
                ),
                "description": (
                    "The booking form recommends only resources whose "
                    "assignment is active, available, and marked recommendable "
                    "here. Rules are per facility: the same equipment can have "
                    "different settings at another facility."
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


class EquipmentPackageComponentInline(admin.TabularInline):
    """Inline editor for package components."""
    model = EquipmentPackageComponent
    extra = 0
    autocomplete_fields = ("equipment",)
    fields = ("equipment", "quantity_per_package", "description")


@admin.register(SoundSystemOperator)
class SoundSystemOperatorAdmin(admin.ModelAdmin):
    """Manage Sound System Operators and their availability."""
    list_display = ("name", "status", "rate", "is_active", "created_at")
    list_filter = ("status", "is_active")
    search_fields = ("name", "contact_phone", "contact_email")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (
            "Operator",
            {"fields": ("name", "status", "is_active")},
        ),
        (
            "Contact",
            {"fields": ("contact_phone", "contact_email")},
        ),
        (
            "Rates",
            {"fields": ("rate",)},
        ),
        (
            "Notes",
            {"fields": ("notes",)},
        ),
        (
            "Metadata",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )


@admin.register(EquipmentPackage)
class EquipmentPackageAdmin(admin.ModelAdmin):
    """Manage equipment packages (e.g., Sound System Package)."""
    list_display = ("name", "package_type", "operator_required", "is_active")
    list_filter = ("package_type", "operator_required", "is_active")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (
            "Package",
            {"fields": ("package_type", "name", "operator_required", "is_active")},
        ),
        (
            "Description",
            {"fields": ("description",)},
        ),
        (
            "Metadata",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )
    inlines = (EquipmentPackageComponentInline,)
