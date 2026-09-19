"""Reservation workflow actions.

Each transition records a ReservationEvent (timeline + approval history) and
emits the appropriate notifications (in-app; email for submission, rejection,
and cancellation only).

Automatic approval emails are intentionally DISABLED: approving a reservation
notifies the requester through the in-app notification system only. Staff can
still send the approval email manually via the admin/API retry action
(``resend_approval_email``).
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from accounts.models import AuditLog
from notifications.models import Notification
from notifications.services import notify, notify_staff
from notifications.email_service import (
    send_reservation_approved,
    send_reservation_cancelled,
    send_reservation_notification,
    send_reservation_rejected,
    send_reservation_submitted,
    resolve_requester_email,
)
from reservations.models import InspectionReport, Reservation, ReservationEvent

logger = logging.getLogger(__name__)


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


class CancellationWindowError(Exception):
    """Raised when a requester tries to cancel a reservation whose event date
    falls within the restricted window (today or tomorrow). Such reservations
    are non-cancellable for requesters; the API layer translates this into an
    HTTP 403."""


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


def _get_requester_email(reservation) -> str:
    """Get the requester's email for notifications.

    For campus users, use their account email. For external requesters,
    use the contact_email from the reservation.
    """
    if reservation.requester and reservation.requester.email:
        return reservation.requester.email
    return reservation.contact_email or ""


def _schedule_approval_email(reservation, actor):
    """Intentionally a no-op: automatic approval emails are disabled.

    Product decision: when an admin approves a reservation, the requester is
    notified through the in-app notification only (created by
    ``approve_reservation``/``auto_approve``); no automatic email is sent.
    Requesters see the updated APPROVED status in the application. The
    delivery-state field is kept for the staff-only manual resend helper.
    """
    return


def resend_approval_email(reservation, actor) -> str:
    """Manually send the approval email for an approved reservation.

    Staff-only (Django admin action / API retry action). Automatic sending on
    approval is disabled; this is the only path that can deliver an approval
    email, and it runs immediately rather than being scheduled. Returns the
    delivery status after the attempt.
    """
    if reservation.status != Reservation.Status.APPROVED:
        raise ValueError("Only approved reservations can receive an approval email.")
    if reservation.approval_email_status == Reservation.ApprovalEmailStatus.SENT:
        return reservation.approval_email_status
    email = resolve_requester_email(reservation, actor)
    if not email:
        reservation.approval_email_status = Reservation.ApprovalEmailStatus.NO_EMAIL
        reservation.save(update_fields=["approval_email_status", "updated_at"])
        logger.warning(
            "Approval email retry skipped for reservation %s: requester has "
            "no valid email address.",
            reservation.reservation_id,
        )
        return reservation.approval_email_status

    # Dispatch immediately and record the delivery state. A failure must
    # never propagate into the caller's transaction — the approval itself is
    # already committed and is unaffected by SMTP problems.
    logger.info(
        "Approval email send attempted for reservation %s to %s.",
        reservation.reservation_id,
        email,
    )
    ok, reason = send_reservation_approved(reservation, actor)
    if ok:
        reservation.approval_email_status = Reservation.ApprovalEmailStatus.SENT
        logger.info(
            "Approval email recorded as SENT for reservation %s.",
            reservation.reservation_id,
        )
    else:
        reservation.approval_email_status = Reservation.ApprovalEmailStatus.FAILED
        logger.error(
            "Approval email delivery FAILED for reservation %s (reason: %s). "
            "Approval itself remains: %s",
            reservation.reservation_id,
            reason,
            reservation.status,
        )
    reservation.save(update_fields=["approval_email_status", "updated_at"])
    return reservation.approval_email_status


def _send_reservation_email(
    reservation,
    status: str,
    status_label: str,
    message: str,
    next_action: str | None = None,
):
    """Send email notification to the requester."""
    email = _get_requester_email(reservation)
    if not email:
        return
    
    send_reservation_notification(
        user_email=email,
        reservation_id=reservation.reservation_id,
        event_name=reservation.event_name,
        facility_name=reservation.facility.name,
        date=reservation.date.isoformat(),
        start_time=reservation.start_time.strftime("%H:%M"),
        end_time=reservation.end_time.strftime("%H:%M"),
        status=status,
        status_label=status_label,
        message=message,
        next_action=next_action,
    )


def auto_approve(reservation, actor, message=""):
    """Approve a reservation without a manual review step.

    Used when an administrator creates a reservation (for a campus user or an
    external organization): those reservations skip the pending queue and are
    immediately confirmed. Records an APPROVED timeline event and notifies the
    requester via email (dispatched after commit).
    """
    from_status = reservation.status
    with transaction.atomic():
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
        if from_status != Reservation.Status.APPROVED:
            _schedule_approval_email(reservation, actor)
    return reservation


def approve_reservation(reservation, actor, comment=""):
    from_status = reservation.status
    if reservation.status != Reservation.Status.PENDING:
        raise ValueError("Only pending reservations can be approved.")
    with transaction.atomic():
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
        _schedule_approval_email(reservation, actor)
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
    # Send email notification
    _send_reservation_email(
        reservation,
        status="REJECTED",
        status_label="Rejected",
        message=f"Your reservation was rejected. Reason: {reason}",
        next_action="Contact the SAS Office if you have questions.",
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
    # Cancellation-window policy: requesters cannot cancel a reservation whose
    # event date is today or tomorrow (even one created days in advance).
    # Staff/admin are exempt — their reservation-management functions are
    # unchanged. Compared against the server's local calendar date (Asia/Manila)
    # using the event date, not the creation date. 2+ days out is cancellable.
    is_requester = (
        reservation.requester_id is not None and actor.id == reservation.requester_id
    )
    days_until_event = (reservation.date - timezone.localdate()).days
    if is_requester and not actor.is_sas_staff and 0 <= days_until_event <= 1:
        raise CancellationWindowError(
            "Reservations scheduled within the next 2 days cannot be cancelled."
        )
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
    # Send email notification
    cancelled_by = "you" if is_requester_cancel else f"{actor.display_name}"
    _send_reservation_email(
        reservation,
        status="CANCELLED",
        status_label="Cancelled",
        message=f"Your reservation was cancelled by {cancelled_by}.",
        next_action="Contact the SAS Office if you need to reschedule.",
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