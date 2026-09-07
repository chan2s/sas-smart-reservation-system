"""Analytics queries and report exports.

All values are derived from live reservation/equipment data — nothing here is
stored or pre-aggregated, so reports always reflect the current state.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime, timedelta

from django.db.models import Count, Sum
from django.db.models.functions import ExtractHour
from django.http import HttpResponse

from equipment.models import Equipment, MaintenanceRecord
from facilities.models import Facility
from reservations.models import Reservation, ReservationItem
from reservations.services.availability import (
    maintenance_quantities,
    reserved_quantities,
)


def _in_range(qs, start=None, end=None):
    if start:
        qs = qs.filter(date__gte=start)
    if end:
        qs = qs.filter(date__lte=end)
    return qs


# ---------------------------------------------------------------------------
# Dashboard + analytics endpoints
# ---------------------------------------------------------------------------

def summary() -> dict:
    today = date.today()
    all_reservations = Reservation.objects.all()
    pending = all_reservations.filter(status=Reservation.Status.PENDING).count()
    facilities_total = Facility.objects.filter(is_active=True).count()
    equipment_total = sum(e.total_quantity for e in Equipment.objects.filter(is_active=True))

    today_qs = all_reservations.filter(
        date=today, status__in=Reservation.ACTIVE_STATUSES
    )
    utilization = facility_utilization(30)

    return {
        "total_reservations": all_reservations.count(),
        "pending_requests": pending,
        "active_today": today_qs.count(),
        "facilities": facilities_total,
        "equipment": equipment_total,
        "campus_reservations": all_reservations.filter(
            requester_type=Reservation.RequesterType.CAMPUS
        ).count(),
        "external_reservations": all_reservations.filter(
            requester_type=Reservation.RequesterType.EXTERNAL
        ).count(),
        "facility_utilization": round(utilization.get("overall", 0), 1),
        "cancellation_rate": cancellation_rate(),
        "no_show_rate": no_show_rate(),
    }


def requester_breakdown(days: int = 365) -> dict:
    """Campus vs external usage, including per-facility external activity.

    Helps SAS understand how much its facilities serve outside organizations.
    """
    start = date.today() - timedelta(days=days)
    qs = Reservation.objects.filter(date__gte=start)

    campus = qs.filter(requester_type=Reservation.RequesterType.CAMPUS).count()
    external = qs.filter(requester_type=Reservation.RequesterType.EXTERNAL).count()

    external_by_facility = (
        qs.filter(
            requester_type=Reservation.RequesterType.EXTERNAL,
            status__in=Reservation.ACTIVE_STATUSES,
        )
        .values("facility__name")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    return {
        "days": days,
        "campus": campus,
        "external": external,
        "external_facility_usage": [
            {"facility": row["facility__name"], "count": row["count"]}
            for row in external_by_facility
        ],
    }


def reservation_trends(months: int = 6) -> list:
    """Reservations per month (counts + status breakdown) for the last N months."""
    from django.db.models.functions import TruncMonth

    cutoff = (date.today().replace(day=1) - timedelta(days=1)).replace(day=1)
    start = cutoff
    for _ in range(max(months - 1, 0)):
        start = (start - timedelta(days=1)).replace(day=1)

    rows = (
        Reservation.objects.filter(created_at__date__gte=start)
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(total=Count("id"))
        .order_by("month")
    )
    by_month = {row["month"]: row["total"] for row in rows}
    result = []
    cursor = start
    while cursor <= cutoff:
        result.append(
            {
                "month": cursor.strftime("%Y-%m"),
                "label": cursor.strftime("%b %Y"),
                "total": by_month.get(cursor, 0),
            }
        )
        next_month = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        cursor = next_month
    return result


def facility_utilization(days: int = 30) -> dict:
    """Share of operating hours booked per facility over the window."""
    start = date.today() - timedelta(days=days)
    facilities = Facility.objects.filter(is_active=True).prefetch_related("operating_hours")
    rows = []
    total_capacity_hours = 0
    total_booked_hours = 0
    for facility in facilities:
        capacity_hours = 0.0
        for oh in facility.operating_hours.all():
            if oh.is_closed:
                continue
            seconds = (
                datetime.combine(date.today(), oh.close_time)
                - datetime.combine(date.today(), oh.open_time)
            ).total_seconds()
            capacity_hours += seconds / 3600

        booked_seconds = 0.0
        for r in Reservation.objects.filter(
            facility=facility, date__gte=start, status__in=Reservation.ACTIVE_STATUSES
        ):
            booked_seconds += (
                datetime.combine(r.date, r.end_time)
                - datetime.combine(r.date, r.start_time)
            ).total_seconds()
        booked_hours = booked_seconds / 3600
        utilization = (
            round((booked_hours / capacity_hours) * 100, 1)
            if capacity_hours
            else 0.0
        )
        total_capacity_hours += capacity_hours
        total_booked_hours += booked_hours
        rows.append(
            {
                "facility_id": facility.id,
                "name": facility.name,
                "capacity_hours": round(capacity_hours, 1),
                "booked_hours": round(booked_hours, 1),
                "utilization": utilization,
            }
        )
    overall = (
        round((total_booked_hours / total_capacity_hours) * 100, 1)
        if total_capacity_hours
        else 0.0
    )
    return {"overall": overall, "facilities": rows, "days": days}


def equipment_utilization() -> dict:
    """Reserved share of each equipment pool plus overall figure."""
    rows = []
    total_qty = 0
    total_reserved = 0
    for eq in Equipment.objects.filter(is_active=True):
        reserved = eq.reservation_items.filter(
            reservation__status__in=Reservation.ACTIVE_STATUSES
        ).aggregate(total=Sum("quantity"))["total"] or 0
        utilization = round((reserved / eq.total_quantity) * 100, 1) if eq.total_quantity else 0
        total_qty += eq.total_quantity
        total_reserved += reserved
        rows.append(
            {
                "equipment_id": eq.id,
                "name": eq.name,
                "category": eq.category.name,
                "total": eq.total_quantity,
                "reserved": reserved,
                "utilization": utilization,
            }
        )
    overall = round((total_reserved / total_qty) * 100, 1) if total_qty else 0.0
    return {"overall": overall, "items": rows}


def cancellation_rate() -> float:
    total = Reservation.objects.exclude(status=Reservation.Status.PENDING).count()
    if not total:
        return 0.0
    cancelled = Reservation.objects.filter(status=Reservation.Status.CANCELLED).count()
    return round((cancelled / total) * 100, 1)


def no_show_rate() -> float:
    """Approved/active reservations past their date that were never checked in."""
    today = date.today()
    no_shows = Reservation.objects.filter(
        date__lt=today,
        status__in=[Reservation.Status.APPROVED, Reservation.Status.ACTIVE],
        checked_in_at__isnull=True,
    ).count()
    denominator = Reservation.objects.exclude(status=Reservation.Status.PENDING).count()
    if not denominator:
        return 0.0
    return round((no_shows / denominator) * 100, 1)


def peak_periods() -> list:
    """Hour buckets ranked by how often reservations start."""
    rows = (
        Reservation.objects.filter(status__in=Reservation.ACTIVE_STATUSES)
        .annotate(hour=ExtractHour("start_time"))
        .values("hour")
        .annotate(count=Count("id"))
        .order_by("-count", "hour")
    )
    return [{"hour": r["hour"], "count": r["count"]} for r in rows]


def most_requested() -> dict:
    facilities = (
        Reservation.objects.filter(status__in=Reservation.ACTIVE_STATUSES)
        .values("facility__name")
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    equipment = (
        ReservationItem.objects.filter(reservation__status__in=Reservation.ACTIVE_STATUSES)
        .values("equipment__name")
        .annotate(quantity=Sum("quantity"))
        .order_by("-quantity")
    )
    return {
        "facilities": list(facilities[:5]),
        "equipment": list(equipment[:5]),
    }


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

REPORTS = [
    {
        "slug": "reservations",
        "title": "Reservation Report",
        "description": "All reservation requests with requester, facility, schedule, resources, and status.",
    },
    {
        "slug": "facility-utilization",
        "title": "Facility Utilization Report",
        "description": "Booked hours and utilization percentage per facility.",
    },
    {
        "slug": "equipment",
        "title": "Equipment Report",
        "description": "Inventory totals, availability, and reserved quantities per item.",
    },
    {
        "slug": "maintenance",
        "title": "Maintenance Report",
        "description": "Open and resolved equipment maintenance records.",
    },
    {
        "slug": "organizations",
        "title": "Organization Report",
        "description": "Reservation activity grouped by requesting organization.",
    },
    {
        "slug": "no-show",
        "title": "No-Show Report",
        "description": "Approved reservations that were never checked in.",
    },
]


def _report_rows(slug: str, start=None, end=None):
    if slug == "reservations":
        qs = _in_range(
            Reservation.objects.select_related("facility", "requester").prefetch_related("items__equipment"),
            start,
            end,
        )
        headers = [
            "Reservation ID", "Event", "Requester Type", "Organization", "Requester",
            "Facility", "Date", "Start", "End", "Participants", "Status",
            "Created By", "Resources",
        ]
        rows = [
            [
                r.reservation_id,
                r.event_name,
                r.get_requester_type_display(),
                r.organization,
                r.requester_display_name,
                r.facility.name,
                r.date.isoformat(),
                r.start_time.strftime("%H:%M"),
                r.end_time.strftime("%H:%M"),
                r.expected_participants,
                r.get_status_display(),
                r.created_by.display_name if r.created_by else "",
                ", ".join(f"{i.quantity}× {i.equipment.name}" for i in r.items.all()),
            ]
            for r in qs
        ]
        return headers, rows

    if slug == "facility-utilization":
        data = facility_utilization(90)
        headers = ["Facility", "Capacity (hours)", "Booked (hours)", "Utilization (%)"]
        rows = [
            [f["name"], f["capacity_hours"], f["booked_hours"], f["utilization"]]
            for f in data["facilities"]
        ]
        return headers, rows

    if slug == "equipment":
        headers = ["Equipment", "Category", "Total", "Available", "Reserved", "Under maintenance", "Condition"]
        rows = []
        reserved = reserved_quantities(None, None, None)
        maintenance = maintenance_quantities()
        for eq in Equipment.objects.select_related("category").filter(is_active=True):
            maint = maintenance.get(eq.id, 0)
            res = reserved.get(eq.id, 0)
            rows.append(
                [
                    eq.name,
                    eq.category.name,
                    eq.total_quantity,
                    max(eq.total_quantity - maint - res, 0),
                    res,
                    maint,
                    eq.get_condition_display(),
                ]
            )
        return headers, rows

    if slug == "maintenance":
        qs = MaintenanceRecord.objects.select_related("equipment", "reported_by").all()
        headers = ["Equipment", "Quantity", "Issue", "Status", "Reported by", "Reported at", "Description"]
        rows = [
            [
                r.equipment.name,
                r.quantity,
                r.get_issue_type_display(),
                r.get_status_display(),
                r.reported_by.display_name if r.reported_by else "",
                r.created_at.isoformat(),
                r.description,
            ]
            for r in qs
        ]
        return headers, rows

    if slug == "organizations":
        qs = _in_range(Reservation.objects.all(), start, end)
        headers = ["Organization", "Reservations", "Total participants", "Facilities"]
        orgs = {}
        for r in qs.select_related("facility"):
            key = r.organization or r.requester_display_name
            entry = orgs.setdefault(key, {"count": 0, "participants": 0, "facilities": set()})
            entry["count"] += 1
            entry["participants"] += r.expected_participants or 0
            entry["facilities"].add(r.facility.name)
        rows = [
            [name, entry["count"], entry["participants"], ", ".join(sorted(entry["facilities"]))]
            for name, entry in sorted(orgs.items(), key=lambda kv: -kv[1]["count"])
        ]
        return headers, rows

    if slug == "no-show":
        qs = Reservation.objects.filter(
            date__lt=date.today(),
            status__in=[Reservation.Status.APPROVED, Reservation.Status.ACTIVE],
            checked_in_at__isnull=True,
        ).select_related("facility", "requester")
        headers = ["Reservation ID", "Event", "Requester", "Facility", "Date", "Status"]
        rows = [
            [r.reservation_id, r.event_name, r.requester_display_name, r.facility.name, r.date.isoformat(), r.get_status_display()]
            for r in qs
        ]
        return headers, rows

    raise ValueError(f"Unknown report: {slug}")


def report_preview(slug: str, start=None, end=None) -> dict:
    headers, rows = _report_rows(slug, start, end)
    return {"headers": headers, "rows": rows, "count": len(rows)}


def export_report(slug: str, fmt: str, start=None, end=None) -> HttpResponse:
    headers, rows = _report_rows(slug, start, end)
    filename = f"{slug}-{date.today().isoformat()}"

    if fmt == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(headers)
        writer.writerows(rows)
        response = HttpResponse(buffer.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{filename}.csv"'
        return response

    if fmt == "xlsx":
        from openpyxl import Workbook
        from openpyxl.styles import Font

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = slug
        sheet.append(headers)
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for row in rows:
            sheet.append(row)
        buffer = io.BytesIO()
        workbook.save(buffer)
        response = HttpResponse(
            buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}.xlsx"'
        return response

    if fmt == "json":
        return HttpResponse(
            json.dumps({"headers": headers, "rows": rows}),
            content_type="application/json",
        )

    raise ValueError(f"Unsupported format: {fmt}")