from django.contrib import admin

from equipment.models import FacilityResource

from .models import Facility, FacilityImage, OperatingHour


class OperatingHourInline(admin.TabularInline):
    model = OperatingHour
    extra = 0


class FacilityResourceInline(admin.TabularInline):
    """Assign the resources/equipment that belong to this facility.

    This is the facility-side view of the relationship; the same rows are
    editable from the equipment side (Equipment admin). No code change is
    needed to add or move a resource between facilities.
    """

    model = FacilityResource
    extra = 0
    autocomplete_fields = ("equipment",)
    fields = (
        "equipment",
        "quantity",
        "status",
        "additional_fee",
        "operator_available",
        "operator_required",
        "operator_fee",
        "display_order",
        "is_active",
    )


class FacilityImageInline(admin.TabularInline):
    """Multiple images per facility, edited right on the Facility page.

    ``extra = 3`` gives the administrator room to add several images in one
    pass. The primary image is shown first by the model ordering, and
    ``is_primary`` / ``order`` let the admin choose the cover image.
    """

    model = FacilityImage
    extra = 3
    fields = ("image", "is_primary", "order")


@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    list_display = ("name", "facility_type", "capacity", "status", "is_active")
    list_filter = ("facility_type", "status")
    search_fields = ("name", "location")
    inlines = [FacilityImageInline, FacilityResourceInline, OperatingHourInline]
