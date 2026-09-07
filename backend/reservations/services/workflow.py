"""Reservation workflow actions.

Each transition records a ReservationEvent (timeline + approval history) and
emits the appropriate notifications.
"""

from __future__ import annotations

from django.utils import timezone

from accounts.models import AuditLog
from notifications.models import Notification
from notifications.services import notify, notify_staff
from reservations.models import InspectionReport, Reservation, ReservationEvent


class CheckInNotOpenError(Exception):
    """Raised when a check-in is attempted before the 3-hour window opens.

    Carries the reservation so the API layer can tell the client exactly when
    check-in becomes available.
    """

    def __init__(self, reservation):
        self.reservation = reservation
        self.check_in_open_time = reservation.check_in_open_time
        super().__init__(
            "Check-in is not available yet. It opens 3 hours before the event start."
        )


def record_event(reservation, event_type, actor=None, message="", from_status="", to_status=""):
    return ReservationEvent.objects.create(
        reservation=reservation,
        actor=actor,
        event_type=event_type,
        from_status=from_status or "",
        to_status=to_status or "",
        message=message,
    )


def _reservation_link(reservation) -> str:
    return f"/reservations/{reservation.id}"


def auto_approve(reservation, actor, message=""):
    """Approve a reservation without a manual review step.

    Used when an administrator creates a reservation (for a campus user or an
    external organization): those reservations skip the pending queue and are
    immediately confirmed. Records an APPROVED timeline event and notifies the
    requester when they have an account (external requesters are no-ops).
    """
    from_status = reservation.status
    reservation.status = Reservation.Status.APPROVED
    reservation.approved_by = actor
    reservation.approved_at = timezone.now()
    reservation.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    record_event(
        reservation,
        ReservationEvent.EventType.APPROVED,
        actor=actor,
        from_status=from_status,
        to_status=reservation.status,
        message=message or "Automatically approved — created by an administrator.",
    )
    AuditLog.record(
        actor,
        AuditLog.Action.RESERVATION_APPROVED,
        object_type="reservation",
        object_id=reservation.reservation_id,
        object_repr=reservation.event_name,
        detail="Auto-approved (administrator-created reservation)",
    )
    notify(
        reservation.requester,
        Notification.Type.RESERVATION,
        "Reservation approved",
        f"{reservation.event_name} on {reservation.date} was automatically approved.",
        _reservation_link(reservation),
    )
    return reservation


def approve_reservation(reservation, actor, comment=""):
    from_status = reservation.status
    if reservation.status != Reservation.Status.PENDING:
        raise ValueError("Only pending reservations can be approved.")
    reservation.status = Reservation.Status.APPROVED
    reservation.approved_by = actor
    reservation.approved_at = timezone.now()
    reservation.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    record_event(
        reservation,
        ReservationEvent.EventType.APPROVED,
        actor=actor,
        from_status=from_status,
        to_status=reservation.status,
        message=comment,
    )
    AuditLog.record(
        actor,
        AuditLog.Action.RESERVATION_APPROVED,
        object_type="reservation",
        object_id=reservation.reservation_id,
        object_repr=reservation.event_name,
        detail=comment,
    )
    notify(
        reservation.requester,
        Notification.Type.RESERVATION,
        "Reservation approved",
        f"{reservation.event_name} on {reservation.date} has been approved.",
        _reservation_link(reservation),
    )
    return reservation


def reject_reservation(reservation, actor, reason):
    from_status = reservation.status
    if not reason:
        raise ValueError("A rejection reason is required.")
    reservation.status = Reservation.Status.REJECTED
    reservation.rejection_reason = reason
    reservation.save(update_fields=["status", "rejection_reason", "updated_at"])
    record_event(
        reservation,
        ReservationEvent.EventType.REJECTED,
        actor=actor,
        from_status=from_status,
        to_status=reservation.status,
        message=reason,
    )
    AuditLog.record(
        actor,
        AuditLog.Action.RESERVATION_REJECTED,
        object_type="reservation",
        object_id=reservation.reservation_id,
        object_repr=reservation.event_name,
        detail=reason,
    )
    notify(
        reservation.requester,
        Notification.Type.RESERVATION,
        "Reservation rejected",
        f"{reservation.event_name} on {reservation.date} was rejected. Reason: {reason}",
        _reservation_link(reservation),
    )
    return reservation


def request_changes(reservation, actor, message):
    from_status = reservation.status
    if not message:
        raise ValueError("A change request message is required.")
    reservation.status = Reservation.Status.PENDING
    reservation.save(update_fields=["status", "updated_at"])
    record_event(
        reservation,
        ReservationEvent.EventType.CHANGES_REQUESTED,
        actor=actor,
        from_status=from_status,
        to_status=reservation.status,
        message=message,
    )
    notify(
        reservation.requester,
        Notification.Type.RESERVATION,
        "Changes requested",
        f"Changes were requested for {reservation.event_name}: {message}",
        _reservation_link(reservation),
    )
    return reservation


def cancel_reservation(reservation, actor, reason=""):
    from_status = reservation.status
    if reservation.status in (Reservation.Status.COMPLETED, Reservation.Status.CANCELLED, Reservation.Status.REJECTED):
        raise ValueError("This reservation can no longer be cancelled.")
    reservation.status = Reservation.Status.CANCELLED
    reservation.save(update_fields=["status", "updated_at"])
    record_event(
        reservation,
        ReservationEvent.EventType.CANCELLED,
        actor=actor,
        from_status=from_status,
        to_status=reservation.status,
        message=reason or "Cancelled",
    )
    AuditLog.record(
        actor,
        AuditLog.Action.RESERVATION_CANCELLED,
        object_type="reservation",
        object_id=reservation.reservation_id,
        object_repr=reservation.event_name,
        detail=reason or "Cancelled",
    )
    is_requester_cancel = (
        reservation.requester_id is not None and actor.id == reservation.requester_id
    )
    if is_requester_cancel:
        notify_staff(
            Notification.Type.RESERVATION,
            "Reservation cancelled",
            f"{reservation.event_name} on {reservation.date} was cancelled by the requester.",
            _reservation_link(reservation),
        )
    else:
        notify(
            reservation.requester,
            Notification.Type.RESERVATION,
            "Reservation cancelled",
            f"{reservation.event_name} on {reservation.date} was cancelled.",
            _reservation_link(reservation),
        )
    return reservation


def check_in_reservation(reservation, actor, override=False):
    """Check a reservation in.

    The check-in window opens 3 hours before the event start. Anyone may check
    in once the window is open. Before it opens, only an administrator who
    explicitly confirms the override (``override=True``) is allowed — the
    backend verifies the role itself; a regular user cannot bypass the window
    by sending the flag.
    """
    if reservation.status not in (Reservation.Status.APPROVED, Reservation.Status.ACTIVE):
        raise ValueError("Only approved reservations can be checked in.")
    now = timezone.now()
    override_used = bool(now < reservation.check_in_open_time and actor.is_admin and override)
    if now < reservation.check_in_open_time and not override_used:
        raise CheckInNotOpenError(reservation)
    from_status = reservation.status
    reservation.status = Reservation.Status.ACTIVE
    reservation.checked_in_at = timezone.now()
    reservation.early_check_in_override = override_used
    reservation.save(
        update_fields=["status", "checked_in_at", "early_check_in_override", "updated_at"]
    )
    record_event(
        reservation,
        ReservationEvent.EventType.CHECKED_IN,
        actor=actor,
        from_status=from_status,
        to_status=reservation.status,
        message=(
            "Early check-in override performed by an administrator before the "
            "standard 3-hour window."
            if override_used
            else "Requester checked in with SAS staff."
        ),
    )
    AuditLog.record(
        actor,
        AuditLog.Action.EARLY_CHECK_IN if override_used else AuditLog.Action.CHECK_IN,
        object_type="reservation",
        object_id=reservation.reservation_id,
        object_repr=reservation.event_name,
        detail=(
            f"Early check-in override — standard window opened at "
            f"{reservation.check_in_open_time:%Y-%m-%d %H:%M}."
            if override_used
            else ""
        ),
    )
    return reservation


def check_out_reservation(reservation, actor, data):
    """Check out a reservation and record the post-event inspection."""
    if reservation.status != Reservation.Status.ACTIVE:
        raise ValueError("Only active reservations can be checked out.")
    from_status = reservation.status

    report, _ = InspectionReport.objects.update_or_create(
        reservation=reservation,
        defaults={
            "facility_condition": data.get("facility_condition", InspectionReport.FacilityCondition.GOOD),
            "equipment_returned": bool(data.get("equipment_returned", False)),
            "missing_items": data.get("missing_items", ""),
            "notes": data.get("notes", ""),
            "reported_by": actor,
        },
    )
    if data.get("photo"):
        report.photo = data["photo"]
        report.save(update_fields=["photo"])

    for item in reservation.items.all():
        item.returned = bool(data.get("equipment_returned", False))
        item.save(update_fields=["returned"])

    reservation.status = Reservation.Status.COMPLETED
    reservation.checked_out_at = timezone.now()
    reservation.save(update_fields=["status", "checked_out_at", "updated_at"])
    record_event(
        reservation,
        ReservationEvent.EventType.CHECKED_OUT,
        actor=actor,
        from_status=from_status,
        to_status=reservation.status,
        message="Reservation checked out and inspected.",
    )
    AuditLog.record(
        actor,
        AuditLog.Action.CHECK_OUT,
        object_type="reservation",
        object_id=reservation.reservation_id,
        object_repr=reservation.event_name,
    )
    return reservation