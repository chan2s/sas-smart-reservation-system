from django.contrib import admin

from .models import Facility, OperatingHour


class OperatingHourInline(admin.TabularInline):
    model = OperatingHour
    extra = 0


@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    list_display = ("name", "facility_type", "capacity", "status", "is_active")
    list_filter = ("facility_type", "status")
    search_fields = ("name", "location")
    inlines = [OperatingHourInline]