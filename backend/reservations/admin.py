from django.contrib import admin

from .models import InspectionReport, Reservation, ReservationEvent, ReservationItem


class ReservationItemInline(admin.TabularInline):
    model = ReservationItem
    extra = 0


class ReservationEventInline(admin.TabularInline):
    model = ReservationEvent
    extra = 0
    readonly_fields = ("event_type", "actor", "message", "created_at")


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ("reservation_id", "event_name", "facility", "date", "start_time", "status", "requester")
    list_filter = ("status", "event_type", "date")
    search_fields = ("reservation_id", "event_name", "organization")
    inlines = [ReservationItemInline, ReservationEventInline]


@admin.register(InspectionReport)
class InspectionReportAdmin(admin.ModelAdmin):
    list_display = ("reservation", "facility_condition", "equipment_returned", "created_at")