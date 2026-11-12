from django.contrib import admin
from django import forms
from django.core.exceptions import ValidationError

from .models import (
    Equipment,
    EquipmentCategory,
    EquipmentImage,
    FacilityResource,
    MaintenanceRecord,
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
        "display_order",
        "is_active",
    )


@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    form = OfficialEquipmentAdminForm
    readonly_fields = ("price",)
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
        ("Display", {"fields": ("display_order", "notes", "is_active")}),
        ("Meta", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(MaintenanceRecord)
class MaintenanceRecordAdmin(admin.ModelAdmin):
    list_display = ("equipment", "quantity", "issue_type", "status", "created_at")
    list_filter = ("issue_type", "status")
