from datetime import date as date_cls

from django.db.models import Sum
from django.utils import timezone

from reservations.models import Reservation

from .models import Equipment, MaintenanceRecord


def _open_maintenance_quantities() -> dict:
    """equipment_id -> quantity currently under open maintenance."""
    qs = (
        MaintenanceRecord.objects.filter(status=MaintenanceRecord.Status.OPEN)
        .values("equipment_id")
        .annotate(total=Sum("quantity"))
    )
    return {row["equipment_id"]: row["total"] for row in qs}


def _reserved_quantities(date_str=None, start=None, end=None, exclude_reservation_id=None, include_all_dates=False) -> dict:
    """equipment_id -> quantity reserved by active reservations on the window.

    Without date/time parameters:
    - If ``include_all_dates=False`` (default): only today's reservations are
      counted. This is for the at-a-glance inventory view, where summing across
      non-overlapping future dates would produce impossible totals.
    - If ``include_all_dates=True``: all active reservations across all dates
      are counted. This is for validation contexts (e.g. preventing inventory
      reduction below committed quantities).

    For a specific date/time window, only reservations whose time range
    overlaps the window are counted.
    """
    items = Reservation.objects.exclude(status=Reservation.Status.REJECTED).exclude(
        status=Reservation.Status.CANCELLED
    )
    if exclude_reservation_id:
        items = items.exclude(pk=exclude_reservation_id)
    if date_str and start and end:
        try:
            target = date_cls.fromisoformat(date_str)
        except (TypeError, ValueError):
            return {}
        items = items.filter(
            date=target,
            start_time__lt=end,
            end_time__gt=start,
            status__in=Reservation.ACTIVE_STATUSES,
        )
    else:
        if include_all_dates:
            items = items.filter(status__in=Reservation.ACTIVE_STATUSES)
        else:
            # At-a-glance: count today's active reservations only.
            # Future reservations don't reduce current availability — items
            # are returned after each event, so they can be re-reserved.
            today = timezone.localdate()
            items = items.filter(
                date=today,
                status__in=Reservation.ACTIVE_STATUSES,
            )
    rows = items.values("items__equipment_id").annotate(total=Sum("items__quantity"))
    return {row["items__equipment_id"]: row["total"] for row in rows}


def committed_quantity(equipment) -> int:
    """Units of ``equipment`` that are committed across all active reservations.

    Reserved by active reservations (all dates) plus units under open
    maintenance. This is the floor below which ``total_quantity`` must never
    be reduced, regardless of when the reservations are scheduled.
    """
    reserved = _reserved_quantities(include_all_dates=True).get(equipment.id, 0)
    maintenance = _open_maintenance_quantities().get(equipment.id, 0)
    return reserved + maintenance


def equipment_availability(equipment, request=None):
    """Per-equipment availability dict shown in list/detail responses.

    ``available`` is schedule-aware: pass ``date``/``start``/``end`` query
    params to compute availability during a specific window, otherwise it is
    an at-a-glance view across all active reservations.

    An item-level status of MAINTENANCE/UNAVAILABLE/RETIRED (or an archived
    item) takes the whole line out of service: available = 0 regardless of
    individual reservation quantities.
    """
    date_str = request.query_params.get("date") if request else None
    start = request.query_params.get("start") if request else None
    end = request.query_params.get("end") if request else None

    maintenance = _open_maintenance_quantities().get(equipment.id, 0)
    reserved = _reserved_quantities(date_str, start, end).get(equipment.id, 0)

    if not equipment.is_active or equipment.status != Equipment.Status.AVAILABLE:
        available = 0
    else:
        available = max(equipment.total_quantity - maintenance - reserved, 0)

    if available == 0:
        availability_status = "UNAVAILABLE"
    elif available < equipment.total_quantity:
        availability_status = "PARTIAL"
    else:
        availability_status = "AVAILABLE"
    return {
        "total": equipment.total_quantity,
        "available": available,
        "reserved": reserved,
        "under_maintenance": maintenance,
        "status": availability_status,
    }


def equipment_stats(request=None) -> dict:
    """Rollup counts for the equipment inventory header.

    Returns both record counts and physical unit counts so the frontend can
    display them with distinct terminology (e.g. "Equipment Types" vs
    "Total Units").
    """
    equipments = list(Equipment.objects.filter(is_active=True))
    maintenance_map = _open_maintenance_quantities()
    reserved_map = _reserved_quantities()

    equipment_types = len(equipments)
    total_units = sum(e.total_quantity for e in equipments)
    available_units = 0
    reserved_units = 0
    under_maintenance_units = 0
    unavailable_units = 0
    damaged_records = 0

    for e in equipments:
        maintenance = maintenance_map.get(e.id, 0)
        reserved = reserved_map.get(e.id, 0)

        # Capped reserved: cannot exceed total_quantity.
        reserved = min(reserved, e.total_quantity)
        reserved_units += reserved

        if e.status != Equipment.Status.AVAILABLE:
            # Item-level status takes the whole line out of service.
            if e.status == Equipment.Status.MAINTENANCE:
                under_maintenance_units += e.total_quantity
            else:
                # UNAVAILABLE or RETIRED
                unavailable_units += e.total_quantity
            continue

        under_maintenance_units += maintenance
        available = max(e.total_quantity - maintenance - reserved, 0)
        available_units += available

        if e.condition in (Equipment.Condition.POOR, Equipment.Condition.DAMAGED):
            damaged_records += 1

    return {
        "equipment_types": equipment_types,
        "total_units": total_units,
        "available_units": available_units,
        "reserved_units": reserved_units,
        "under_maintenance_units": under_maintenance_units,
        "unavailable_units": unavailable_units,
        "damaged_records": damaged_records,
    }


def equipment_usage_history(equipment_id: int) -> list:
    """Reservation usage rows for the equipment detail page (most recent first)."""
    from reservations.models import ReservationItem

    rows = (
        ReservationItem.objects.filter(equipment_id=equipment_id)
        .select_related("reservation")
        .order_by("-reservation__date", "-reservation__start_time")
    )
    return [
        {
            "reservation": item.reservation.id,
            "reservation_id": item.reservation.reservation_id,
            "event_name": item.reservation.event_name,
            "date": item.reservation.date.isoformat(),
            "quantity": item.quantity,
            "status": item.reservation.status,
            "status_label": item.reservation.get_status_display(),
        }
        for item in rows
    ]


def reconcile_status(equipment) -> None:
    """Keep the item-level status consistent with open maintenance records.

    * If every unit is under open maintenance, the item is fully out of
      service (status = MAINTENANCE).
    * If only some units are under maintenance, the item stays AVAILABLE so
      the remaining units can still be reserved.
    """
    open_quantity = _open_maintenance_quantities().get(equipment.id, 0)
    if open_quantity >= equipment.total_quantity:
        if equipment.status != Equipment.Status.MAINTENANCE:
            equipment.status = Equipment.Status.MAINTENANCE
            equipment.save(update_fields=["status", "updated_at"])
    elif equipment.status == Equipment.Status.MAINTENANCE:
        equipment.status = Equipment.Status.AVAILABLE
        equipment.save(update_fields=["status", "updated_at"])