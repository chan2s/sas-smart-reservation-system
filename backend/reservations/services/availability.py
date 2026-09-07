"""Availability engine.

Given a facility, date, time window, and requested equipment quantities, this
module reports exactly what is available, what conflicts exist, and proposes
alternative time slots that satisfy every requested resource.
"""

from __future__ import annotations

from datetime import date as date_cls
from datetime import datetime, time as time_cls, timedelta

from django.db.models import Sum

from equipment.models import Equipment, MaintenanceRecord
from facilities.models import Facility, OperatingHour
from reservations.models import Reservation


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def overlapping_reservations(facility_id, target_date, start, end, exclude_id=None):
    """Reservations that hold the facility during [start, end) on target_date."""
    qs = Reservation.objects.filter(
        facility_id=facility_id,
        date=target_date,
        status__in=Reservation.ACTIVE_STATUSES,
        start_time__lt=end,
        end_time__gt=start,
    )
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    return qs


def reserved_quantities(target_date, start, end, exclude_id=None) -> dict:
    """equipment_id -> quantity requested by overlapping active reservations.

    When ``target_date`` (or start/end) is ``None`` the corresponding filter is
    skipped, returning quantities reserved across all windows.
    """
    qs = Reservation.objects.filter(status__in=Reservation.ACTIVE_STATUSES)
    if target_date is not None:
        qs = qs.filter(date=target_date)
    if start is not None and end is not None:
        qs = qs.filter(start_time__lt=end, end_time__gt=start)
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    rows = qs.values("items__equipment_id").annotate(total=Sum("items__quantity"))
    return {row["items__equipment_id"]: row["total"] for row in rows}


def maintenance_quantities() -> dict:
    """equipment_id -> quantity under open maintenance."""
    rows = (
        MaintenanceRecord.objects.filter(status=MaintenanceRecord.Status.OPEN)
        .values("equipment_id")
        .annotate(total=Sum("quantity"))
    )
    return {row["equipment_id"]: row["total"] for row in rows}


def operating_hour_for(facility, target_date):
    try:
        return facility.operating_hours.get(day_of_week=target_date.weekday())
    except OperatingHour.DoesNotExist:
        return None


def equipment_availability_map(target_date, start, end, exclude_id=None) -> dict:
    """id -> {total, reserved, under_maintenance, available} for every active item.

    Items whose status is not AVAILABLE (e.g. under maintenance, retired) or
    that are archived report ``available = 0`` so they can never be reserved,
    while still being visible to the availability report.
    """
    reserved = reserved_quantities(target_date, start, end, exclude_id)
    maintenance = maintenance_quantities()
    result = {}
    for eq in Equipment.objects.filter(is_active=True).only(
        "id", "name", "total_quantity", "condition", "status"
    ):
        reserved_qty = reserved.get(eq.id, 0)
        maint_qty = maintenance.get(eq.id, 0)
        if eq.status != Equipment.Status.AVAILABLE:
            available_qty = 0
        else:
            available_qty = max(eq.total_quantity - reserved_qty - maint_qty, 0)
        result[eq.id] = {
            "total": eq.total_quantity,
            "reserved": reserved_qty,
            "under_maintenance": maint_qty,
            "available": available_qty,
        }
    return result


# ---------------------------------------------------------------------------
# Core check
# ---------------------------------------------------------------------------

def check_availability(facility_id, target_date, start, end, items=None, exclude_id=None) -> dict:
    """Analyse a proposed reservation window.

    ``items`` is a list of ``{"equipment_id": int, "quantity": int}``.
    Returns a structured availability report (see ``availability_report``).
    """
    facility = Facility.objects.get(pk=facility_id)

    # Facility conflicts ----------------------------------------------------
    overlaps = list(
        overlapping_reservations(facility_id, target_date, start, end, exclude_id)
        .select_related("requester")
        .order_by("start_time")
    )
    facility_ok = not overlaps and facility.status == Facility.Status.OPERATIONAL

    # Operating hours -------------------------------------------------------
    oh = operating_hour_for(facility, target_date)
    hours_ok = False
    if oh and not oh.is_closed:
        hours_ok = start >= oh.open_time and end <= oh.close_time

    # Equipment -------------------------------------------------------------
    av = equipment_availability_map(target_date, start, end, exclude_id)
    item_results = []
    for item in items or []:
        eq_id = int(item["equipment_id"])
        quantity = int(item.get("quantity", 1))
        info = av.get(eq_id)
        if info is None:
            item_results.append(
                {
                    "equipment_id": eq_id,
                    "name": None,
                    "category": None,
                    "requested": quantity,
                    "available": 0,
                    "status": "UNAVAILABLE",
                    "message": "Equipment record not found or inactive.",
                }
            )
            continue
        eq = Equipment.objects.filter(pk=eq_id).first()
        if quantity <= info["available"]:
            status = "AVAILABLE"
            message = ""
        elif info["available"] > 0:
            status = "PARTIAL"
            message = (
                f"Only {info['available']} {eq.name} available. "
                f"You requested {quantity}."
            )
        else:
            status = "UNAVAILABLE"
            message = (
                f"No {eq.name} available at this time. You requested {quantity}."
            )
        item_results.append(
            {
                "equipment_id": eq_id,
                "name": eq.name if eq else None,
                "category": eq.category.name if eq else None,
                "requested": quantity,
                "available": info["available"],
                "total": info["total"],
                "status": status,
                "message": message,
            }
        )

    problems = []
    if not facility_ok:
        if overlaps:
            problems.append(
                {
                    "type": "facility",
                    "message": (
                        f"The {facility.name} is already reserved during this time."
                    ),
                }
            )
        else:
            problems.append(
                {
                    "type": "facility",
                    "message": f"The {facility.name} is currently under maintenance.",
                }
            )
    if not hours_ok:
        problems.append(
            {
                "type": "hours",
                "message": (
                    "The requested time is outside the facility's operating hours."
                    if oh
                    else "The facility has no operating hours configured for this day."
                ),
            }
        )
    for res in item_results:
        if res["status"] in ("PARTIAL", "UNAVAILABLE"):
            problems.append({"type": "equipment", "message": res["message"]})

    overall_ok = not problems

    return availability_report(
        facility=facility,
        target_date=target_date,
        start=start,
        end=end,
        overlaps=overlaps,
        hours_ok=hours_ok,
        operating_hour=oh,
        item_results=item_results,
        overall_ok=overall_ok,
        problems=problems,
    )


def availability_report(
    facility,
    target_date,
    start,
    end,
    overlaps,
    hours_ok,
    operating_hour,
    item_results,
    overall_ok,
    problems,
) -> dict:
    return {
        "facility": {
            "id": facility.id,
            "name": facility.name,
            "status": facility.status,
            "available": overall_ok
            and not overlaps
            and facility.status == Facility.Status.OPERATIONAL,
            "operating_hours": {
                "open": operating_hour.open_time.strftime("%H:%M") if operating_hour and not operating_hour.is_closed else None,
                "close": operating_hour.close_time.strftime("%H:%M") if operating_hour and not operating_hour.is_closed else None,
                "within_hours": hours_ok,
            }
            if operating_hour
            else None,
            "conflicts": [
                {
                    "reservation_id": r.reservation_id,
                    "event_name": r.event_name,
                    "start_time": r.start_time.strftime("%H:%M"),
                    "end_time": r.end_time.strftime("%H:%M"),
                    "status": r.status,
                    # External reservations have no requester account.
                    "requester": r.requester_display_name,
                }
                for r in overlaps
            ],
        },
        "items": item_results,
        "problems": problems,
        "overall": {
            "ok": overall_ok,
            "message": "" if overall_ok else "Resource conflict detected",
        },
        "requested": {
            "date": target_date.isoformat(),
            "start_time": start.strftime("%H:%M"),
            "end_time": end.strftime("%H:%M"),
        },
    }


# ---------------------------------------------------------------------------
# Alternative scheduling
# ---------------------------------------------------------------------------

def find_alternatives(
    facility_id,
    target_date,
    start,
    end,
    items=None,
    days=14,
    limit=3,
    buffer_minutes=30,
):
    """Propose up to ``limit`` fully-available time slots.

    Candidates are generated from the facility's opening time and from just
    after each existing reservation ends, which yields realistic adjacent
    slots. A buffer is applied between consecutive reservations.
    """
    facility = Facility.objects.get(pk=facility_id)
    duration = datetime.combine(target_date, end) - datetime.combine(target_date, start)
    items = items or []
    results = []

    for offset in range(0, days):
        day = target_date + timedelta(days=offset)
        oh = operating_hour_for(facility, day)
        if oh is None or oh.is_closed:
            continue

        candidates = [oh.open_time]
        existing = list(
            Reservation.objects.filter(
                facility=facility,
                date=day,
                status__in=Reservation.ACTIVE_STATUSES,
            ).order_by("start_time")
        )
        for r in existing:
            candidate = (
                datetime.combine(day, r.end_time) + timedelta(minutes=buffer_minutes)
            ).time()
            candidates.append(candidate)

        seen = set()
        for candidate in sorted(set(candidates)):
            if candidate in seen:
                continue
            seen.add(candidate)
            candidate_end = (
                datetime.combine(day, candidate) + duration
            ).time()
            if candidate_end > oh.close_time:
                continue
            if day == target_date and candidate == start and candidate_end == end:
                continue

            report = check_availability(
                facility_id, day, candidate, candidate_end, items
            )
            if report["overall"]["ok"]:
                results.append(
                    {
                        "date": day.isoformat(),
                        "start_time": candidate.strftime("%H:%M"),
                        "end_time": candidate_end.strftime("%H:%M"),
                        "duration": str(duration),
                    }
                )
                if len(results) >= limit:
                    return results
    return results