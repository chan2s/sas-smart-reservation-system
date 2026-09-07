from datetime import date as date_cls

from reservations.models import Reservation


def facility_availability_summary(facility, date_str=None) -> dict:
    """Lightweight availability snapshot shown on facility cards."""
    summary = {
        "status": facility.status,
        "is_operational": facility.status == facility.Status.OPERATIONAL,
    }
    if not date_str:
        return summary

    try:
        target = date_cls.fromisoformat(date_str)
    except (TypeError, ValueError):
        return summary

    overlaps = (
        Reservation.objects.filter(
            facility=facility,
            date=target,
            status__in=Reservation.ACTIVE_STATUSES,
        )
        .exclude(status=Reservation.Status.REJECTED)
        .count()
    )
    summary["date"] = date_str
    summary["overlapping_reservations"] = overlaps
    summary["available"] = overlaps == 0 and summary["is_operational"]
    return summary