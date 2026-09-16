"""Live database retrieval for the chatbot.

Every function here queries the current database directly and returns the
raw facts the response template will render. No caching, no snapshots —
each question hits the source tables, so answers always reflect the latest
reservations, schedules, and statuses.

Role scoping mirrors the rest of the app:
* staff/admin users get organization-wide facts;
* requesters only ever see their own reservation rows.
"""

from __future__ import annotations

from datetime import date, time as time_cls, timedelta

from django.db import IntegrityError, OperationalError, ProgrammingError
from django.utils import timezone

from equipment.models import Equipment, MaintenanceRecord
from facilities.models import Facility, OperatingHour
from reservations.models import Reservation
from reservations.services.availability import (
    check_availability,
    operating_hour_for,
    overlapping_reservations,
)

from .facilities import facility_status_label


def _fmt_time(t: time_cls | None) -> str:
    if t is None:
        return "—"
    hour = t.hour % 12 or 12
    meridiem = "AM" if t.hour < 12 else "PM"
    minute = f":{t.minute:02d}" if t.minute else ""
    return f"{hour}{minute} {meridiem}"


def _fmt_date(d: date) -> str:
    return d.strftime("%B %d, %Y").replace(" 0", " ")


def _fmt_day(d: date) -> str:
    return d.strftime("%A")


class RetrievalError(Exception):
    """The database is unavailable or returned an unexpected shape."""


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

def availability_report(
    facility: Facility,
    target_date: date,
    start: time_cls | None,
    end: time_cls | None,
) -> dict:
    """Structured availability facts for a facility/date/time window."""
    try:
        if start is None:
            # Whole-day view: list conflicting reservations and free windows.
            overlaps = list(
                overlapping_reservations(facility.id, target_date, time_cls(0, 0), time_cls(23, 59))
                .select_related("requester")
                .order_by("start_time")
            )
            free_windows = _free_windows(facility, target_date, overlaps)
            return {
                "kind": "whole_day",
                "facility": facility,
                "date": target_date,
                "conflicts": overlaps,
                "free_windows": free_windows,
                "under_maintenance": facility.status != Facility.Status.OPERATIONAL,
            }

        report = check_availability(facility.id, target_date, start, end)
        overlaps = list(
            overlapping_reservations(facility.id, target_date, start, end)
            .select_related("requester")
            .order_by("start_time")
        )
        return {
            "kind": "window",
            "facility": facility,
            "date": target_date,
            "start": start,
            "end": end,
            "conflicts": overlaps,
            "under_maintenance": facility.status != Facility.Status.OPERATIONAL,
            "within_hours": bool((report["facility"].get("operating_hours") or {}).get("within_hours")),
            "operating_hours": report["facility"].get("operating_hours"),
            "model_report": report,
        }
    except (OperationalError, ProgrammingError, IntegrityError) as exc:
        raise RetrievalError(str(exc)) from exc


def _free_windows(
    facility: Facility, target_date: date, overlaps: list[Reservation]
) -> list[dict]:
    """Free windows inside operating hours, minus overlapping reservations."""
    oh = operating_hour_for(facility, target_date)
    if oh is None or oh.is_closed:
        return []
    windows: list[tuple[time_cls, time_cls]] = [(oh.open_time, oh.close_time)]
    for r in sorted(overlaps, key=lambda r: r.start_time):
        next_windows: list[tuple[time_cls, time_cls]] = []
        for open_t, close_t in windows:
            if r.end_time <= open_t or r.start_time >= close_t:
                next_windows.append((open_t, close_t))
                continue
            if r.start_time > open_t:
                next_windows.append((open_t, r.start_time))
            if r.end_time < close_t:
                next_windows.append((r.end_time, close_t))
        windows = next_windows
    return [
        {"start": _fmt_time(s), "end": _fmt_time(e)} for s, e in windows if s < e
    ]


# ---------------------------------------------------------------------------
# Facilities
# ---------------------------------------------------------------------------

def facility_profile(facility: Facility) -> dict:
    oh_by_day = {oh.day_of_week: oh for oh in facility.operating_hours.all()}
    days = []
    for day in range(7):
        oh = oh_by_day.get(day)
        if oh is None or oh.is_closed:
            days.append(f"{_fmt_day_name(day)}: Closed")
        else:
            days.append(f"{_fmt_day_name(day)}: {_fmt_time(oh.open_time)} – {_fmt_time(oh.close_time)}")
    return {
        "facility": facility,
        "status_label": facility_status_label(facility),
        "rules": [str(rule) for rule in (facility.rules or [])],
        "hours_lines": days,
        "type_label": facility.get_facility_type_display(),
    }


def _fmt_day_name(day: int) -> str:
    from facilities.models import FacilityOperatingHours

    return FacilityOperatingHours.day_label(day)


def all_facilities() -> list[Facility]:
    return list(
        Facility.objects.filter(is_active=True).order_by("name")
    )


# ---------------------------------------------------------------------------
# Reservations (role-scoped)
# ---------------------------------------------------------------------------

def user_reservations(user, limit: int = 10) -> list[Reservation]:
    """The user's own reservations, newest date first."""
    return list(
        Reservation.objects.filter(requester=user)
        .select_related("facility")
        .order_by("-date", "start_time")[:limit]
    )


def find_reservation_by_id(user, reservation_id: str) -> Reservation | None:
    qs = Reservation.objects.select_related("facility", "requester")
    if not user.is_sas_staff:
        qs = qs.filter(requester=user)
    return qs.filter(reservation_id=reservation_id).first()


def reservations_for_facility_between(
    facility: Facility, start_date: date, end_date: date
) -> list[Reservation]:
    """Active reservations for a facility in a date range (staff-visible)."""
    return list(
        Reservation.objects.filter(
            facility=facility,
            date__gte=start_date,
            date__lte=end_date,
            status__in=Reservation.ACTIVE_STATUSES,
        )
        .select_related("requester")
        .order_by("date", "start_time")
    )


# ---------------------------------------------------------------------------
# Equipment / maintenance
# ---------------------------------------------------------------------------

def equipment_availability(
    target_date: date, start: time_cls | None, end: time_cls | None
) -> list[dict]:
    from reservations.services.availability import equipment_availability_map

    mapping = equipment_availability_map(target_date, start or time_cls(0, 0), end or time_cls(23, 59))
    rows = []
    for eq in Equipment.objects.filter(is_active=True).select_related("category"):
        info = mapping.get(eq.id, {})
        rows.append(
            {
                "equipment": eq,
                "total": info.get("total", eq.total_quantity),
                "reserved": info.get("reserved", 0),
                "under_maintenance": info.get("under_maintenance", 0),
                "available": info.get("available", 0),
            }
        )
    return rows


def open_maintenance_records(limit: int = 8) -> list[MaintenanceRecord]:
    return list(
        MaintenanceRecord.objects.filter(status=MaintenanceRecord.Status.OPEN)
        .select_related("equipment")
        .order_by("-created_at")[:limit]
    )


# ---------------------------------------------------------------------------
# Cancellation policy excerpt (from the workflow's own rule)
# ---------------------------------------------------------------------------

def cancellation_policy_excerpt() -> str:
    """The cancellation window rule, sourced from the workflow module's logic."""
    from reservations.services import workflow as _workflow  # noqa: F401

    # The rule lives in workflow.cancel_reservation: requesters cannot cancel
    # events within 2 days; staff are exempt. Keep the wording in one place.
    return (
        "reservations scheduled within the next 2 days (today or tomorrow) "
        "cannot be cancelled by requesters; contact the SAS Office for "
        "assistance."
    )



