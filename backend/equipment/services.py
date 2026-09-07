from datetime import date as date_cls

from django.db.models import Sum

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


def _reserved_quantities(date_str=None, start=None, end=None, exclude_reservation_id=None) -> dict:
    """equipment_id -> quantity reserved by active reservations on the window.

    Without date/time parameters, quantities reserved by all active
    reservations are returned (useful for an at-a-glance inventory).
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
        items = items.filter(status__in=Reservation.ACTIVE_STATUSES)
    rows = items.values("items__equipment_id").annotate(total=Sum("items__quantity"))
    return {row["items__equipment_id"]: row["total"] for row in rows}


def committed_quantity(equipment) -> int:
    """Units of ``equipment`` that are unavailable right now.

    Reserved by active reservations plus units under open maintenance. This is
    the floor below which ``total_quantity`` must never be reduced.
    """
    reserved = _reserved_quantities().get(equipment.id, 0)
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
    """Rollup counts for the equipment inventory header."""
    equipments = list(Equipment.objects.filter(is_active=True))
    maintenance_map = _open_maintenance_quantities()
    reserved_map = _reserved_quantities()

    total = sum(e.total_quantity for e in equipments)
    available = 0
    for e in equipments:
        if e.status != Equipment.Status.AVAILABLE:
            continue
        maintenance = maintenance_map.get(e.id, 0)
        reserved = reserved_map.get(e.id, 0)
        available += max(e.total_quantity - maintenance - reserved, 0)

    return {
        "total": total,
        "available": available,
        "reserved": sum(reserved_map.values()),
        "under_maintenance": sum(maintenance_map.values()),
        "unavailable": sum(
            e.total_quantity
            for e in equipments
            if e.status in (Equipment.Status.UNAVAILABLE, Equipment.Status.RETIRED)
        ),
        "damaged": Equipment.objects.filter(
            is_active=True,
            condition__in=[Equipment.Condition.POOR, Equipment.Condition.DAMAGED],
        ).count(),
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