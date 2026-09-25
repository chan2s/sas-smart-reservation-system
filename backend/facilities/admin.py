from django.contrib import admin

from .models import Facility, FacilityImage, OperatingHour


class OperatingHourInline(admin.TabularInline):
    model = OperatingHour
    extra = 0


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
    inlines = [FacilityImageInline, OperatingHourInline]
