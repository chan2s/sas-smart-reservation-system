"""Reschedule-request workflow.

Requesters only ever *propose* a new schedule: an administrator reviews the
OTP-verified request and applies it. Approval re-checks availability, updates
the existing reservation in place (preserving its id, reference, documents, and
payment history), and recalculates fees with the existing pricing service.
"""

from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from accounts.models import AuditLog
from notifications.models import Notification
from notifications.services import notify, notify_staff
from reservations.models import (
    Reservation,
    ReservationEvent,
    RescheduleRequest,
)
from reservations.services.availability import check_availability
from reservations.services.pricing import snapshot_reservation_fees
from reservations.services.workflow import record_event


class RescheduleUnavailable(ValueError):
    """Raised when a requested schedule fails availability checks on approval."""

    def __init__(self, message, report):
        super().__init__(message)
        self.report = report


def reservation_items_payload(reservation):
    return [
        {"equipment_id": item.equipment_id, "quantity": item.quantity}
        for item in reservation.items.all()
    ]


def availability_for(reservation, target_date, start, end):
    """Availability for a proposed slot, excluding the reservation's own slot."""
    return check_availability(
        reservation.facility_id,
        target_date,
        start,
        end,
        reservation_items_payload(reservation),
        exclude_id=reservation.pk,
    )


def _email(reservation):
    if reservation.requester_id and reservation.requester.email:
        return reservation.requester.email.strip()
    return (reservation.contact_email or "").strip()


def _reservation_link(reservation):
    return f"/reservations/{reservation.id}"


def _regenerate_letter_and_resend_email(reservation_id, actor_id):
    """Refresh the approval letter for a rescheduled reservation, then email it.

    Runs after the reschedule transaction commits so it always reads the final
    saved schedule. The previous letter is replaced by the existing generation
    workflow before anything is attached, so an outdated document can never be
    sent. Every outcome is recorded on the reservation timeline and the
    reservation remains approved; staff can retry from the reservation page.
    """
    from django.contrib.auth import get_user_model

    from reservations.services.approval_documents import generate_approval_documents
    from reservations.services.workflow import resend_approval_email

    reservation = Reservation.objects.filter(pk=reservation_id).first()
    if reservation is None:
        return
    actor = (
        get_user_model().objects.filter(pk=actor_id).first() if actor_id else None
    )
    schedule = (
        f"{reservation.date} "
        f"{reservation.start_time:%H:%M}–{reservation.end_time:%H:%M}"
    )

    try:
        generate_approval_documents(reservation, regenerate=True)
    except Exception as exc:  # noqa: BLE001 - the approval stays committed
        record_event(
            reservation,
            ReservationEvent.EventType.APPROVAL_LETTER_REGENERATED,
            actor=actor,
            from_status=reservation.status,
            to_status=reservation.status,
            message=(
                f"Approval letter regeneration failed for the rescheduled "
                f"schedule ({schedule}): "
                f"{reservation.generated_approval_error or type(exc).__name__}."
            ),
        )
        return
    reservation.refresh_from_db()
    record_event(
        reservation,
        ReservationEvent.EventType.APPROVAL_LETTER_REGENERATED,
        actor=actor,
        from_status=reservation.status,
        to_status=reservation.status,
        message=(
            f"Approval letter regenerated with the rescheduled date and time "
            f"({schedule})."
        ),
    )

    recipient = _email(reservation)
    try:
        status = resend_approval_email(reservation, actor, force=True)
    except Exception as exc:  # noqa: BLE001 - retain the new letter
        record_event(
            reservation,
            ReservationEvent.EventType.APPROVAL_EMAIL_RESENT,
            actor=actor,
            from_status=reservation.status,
            to_status=reservation.status,
            message=(
                f"Approval email with the regenerated letter could not be sent: "
                f"{type(exc).__name__}."
            ),
            recipient_email=recipient,
        )
        return
    reservation.refresh_from_db()
    if status == Reservation.ApprovalEmailStatus.SENT:
        message = (
            "Approval email with the regenerated approval letter was sent to "
            "the registered representative address."
        )
    elif status == Reservation.ApprovalEmailStatus.NO_EMAIL:
        message = (
            "Approval email was not sent because no registered representative "
            "email address is available."
        )
    else:
        reason = reservation.approval_email_last_error or "delivery_failed"
        message = (
            f"Approval email with the regenerated letter could not be delivered "
            f"({reason}). The new letter remains available for retry."
        )
    record_event(
        reservation,
        ReservationEvent.EventType.APPROVAL_EMAIL_RESENT,
        actor=actor,
        from_status=reservation.status,
        to_status=reservation.status,
        message=message,
        recipient_email=recipient,
    )


def _review_guard(reschedule_request, actor):
    """Only GSO staff may decide a request, and never their own."""
    if not getattr(actor, "is_gso_staff", False):
        raise PermissionDenied("Only GSO staff can review reschedule requests.")
    if reschedule_request.reservation.requester_id is not None:
        if reschedule_request.reservation.requester_id == actor.id:
            raise PermissionDenied(
                "You cannot review your own reschedule request."
            )


def approve(reschedule_request, actor, comment=""):
    """Apply the requested schedule to the existing reservation.

    The caller passes a request row already resolved through the staff-only
    API. Everything is re-checked under row locks: the request must still be
    pending, the reservation still approved and not started, and the proposed
    slot still available. Fees are recalculated from current pricing rules.
    """
    _review_guard(reschedule_request, actor)

    with transaction.atomic():
        request_row = RescheduleRequest.objects.select_for_update().get(
            pk=reschedule_request.pk
        )
        reservation = Reservation.objects.select_for_update().get(
            pk=request_row.reservation_id
        )
        if request_row.status != RescheduleRequest.Status.PENDING:
            raise ValueError("This reschedule request has already been reviewed.")
        if reservation.status != Reservation.Status.APPROVED:
            raise ValueError(
                "Only an approved reservation can be rescheduled."
            )
        if reservation.has_started:
            raise ValueError(
                "This reservation has already started and cannot be rescheduled."
            )

        report = availability_for(
            reservation,
            request_row.requested_date,
            request_row.requested_start_time,
            request_row.requested_end_time,
        )
        if not report["overall"]["ok"]:
            raise RescheduleUnavailable(
                "The requested schedule is unavailable. Reject the request or "
                "coordinate another schedule with the requester.",
                report,
            )

        previous = (
            f"{reservation.date} "
            f"{reservation.start_time:%H:%M}–{reservation.end_time:%H:%M}"
        )
        reservation.date = request_row.requested_date
        reservation.start_time = request_row.requested_start_time
        reservation.end_time = request_row.requested_end_time
        update_fields = ["date", "start_time", "end_time", "updated_at"]
        if reservation.requester_type == Reservation.RequesterType.EXTERNAL:
            # The previous approval email described the old schedule. Show it
            # as pending until the regenerated letter is actually delivered.
            reservation.approval_email_status = (
                Reservation.ApprovalEmailStatus.NOT_SENT
            )
            reservation.approval_email_last_error = ""
            update_fields.extend(
                ["approval_email_status", "approval_email_last_error"]
            )
        reservation.save(update_fields=update_fields)
        # Same pricing logic as a fresh reservation: snapshotted line items and
        # the derived required payment are recalculated, never client-supplied.
        snapshot_reservation_fees(reservation)

        request_row.status = RescheduleRequest.Status.APPROVED
        request_row.reviewed_by = actor
        request_row.reviewed_at = timezone.now()
        request_row.admin_message = comment
        request_row.save(
            update_fields=[
                "status",
                "reviewed_by",
                "reviewed_at",
                "admin_message",
                "updated_at",
            ]
        )

        new_schedule = (
            f"{reservation.date} "
            f"{reservation.start_time:%H:%M}–{reservation.end_time:%H:%M}"
        )
        event = record_event(
            reservation,
            ReservationEvent.EventType.RESCHEDULED,
            actor=actor,
            from_status=reservation.status,
            to_status=reservation.status,
            message=(
                f"Reservation rescheduled from {previous} to {new_schedule}. "
                f"Requester's reason: {request_row.reason}"
            ),
        )
        AuditLog.record(
            actor,
            AuditLog.Action.RESERVATION_EDITED,
            object_type="reservation",
            object_id=reservation.reservation_id,
            object_repr=reservation.event_name,
            detail=f"Rescheduled from {previous} to {new_schedule}.",
        )
        notify(
            reservation.requester,
            Notification.Type.RESERVATION,
            "Reschedule approved",
            f"{reservation.event_name} was moved to {new_schedule}.",
            _reservation_link(reservation),
            event_key=f"reservation-event:{event.pk}:reschedule-approved",
        )
        notify_staff(
            Notification.Type.RESERVATION,
            "Reservation rescheduled",
            f"{reservation.event_name} was moved to {new_schedule}.",
            _reservation_link(reservation),
            exclude_user=actor,
            event_key=f"reservation-event:{event.pk}:reschedule-approved-staff",
        )

        recipient = _email(reservation)
        if reservation.requester_type == Reservation.RequesterType.EXTERNAL:
            # The external approval letter carries the schedule. Regenerate it
            # from the committed reservation and resend it, instead of sending
            # a separate schedule notice with the old letter.
            transaction.on_commit(
                lambda pk=reservation.pk, actor_id=actor.pk: (
                    _regenerate_letter_and_resend_email(pk, actor_id)
                ),
                robust=True,
            )
        elif recipient:
            from notifications.email_service import send_reschedule_approved

            transaction.on_commit(
                lambda current=reservation, req=request_row, to=recipient: (
                    send_reschedule_approved(current, req, to)
                ),
                robust=True,
            )
    return request_row


def reject(reschedule_request, actor, reason):
    """Reject a pending request without touching the reservation."""
    _review_guard(reschedule_request, actor)
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("A rejection reason is required.")

    with transaction.atomic():
        request_row = RescheduleRequest.objects.select_for_update().get(
            pk=reschedule_request.pk
        )
        if request_row.status != RescheduleRequest.Status.PENDING:
            raise ValueError("This reschedule request has already been reviewed.")
        reservation = request_row.reservation
        request_row.status = RescheduleRequest.Status.REJECTED
        request_row.rejection_reason = reason
        request_row.reviewed_by = actor
        request_row.reviewed_at = timezone.now()
        request_row.save(
            update_fields=[
                "status",
                "rejection_reason",
                "reviewed_by",
                "reviewed_at",
                "updated_at",
            ]
        )
        event = record_event(
            reservation,
            ReservationEvent.EventType.RESCHEDULE_REJECTED,
            actor=actor,
            from_status=reservation.status,
            to_status=reservation.status,
            message=f"Reschedule request rejected: {reason}",
        )
        notify(
            reservation.requester,
            Notification.Type.RESERVATION,
            "Reschedule request rejected",
            f"The reschedule request for {reservation.event_name} was rejected: {reason}",
            _reservation_link(reservation),
            event_key=f"reservation-event:{event.pk}:reschedule-rejected",
        )
        recipient = _email(reservation)
        if recipient:
            from notifications.email_service import send_reschedule_rejected

            transaction.on_commit(
                lambda current=reservation, req=request_row, to=recipient: (
                    send_reschedule_rejected(current, req, to)
                ),
                robust=True,
            )
    return request_row


def request_more_information(reschedule_request, actor, message):
    """Ask the requester for clarification; the request stays open for review."""
    _review_guard(reschedule_request, actor)
    message = (message or "").strip()
    if not message:
        raise ValueError("A message is required when requesting more information.")

    with transaction.atomic():
        request_row = RescheduleRequest.objects.select_for_update().get(
            pk=reschedule_request.pk
        )
        if request_row.status != RescheduleRequest.Status.PENDING:
            raise ValueError("This reschedule request has already been reviewed.")
        reservation = request_row.reservation
        request_row.status = RescheduleRequest.Status.INFO_REQUIRED
        request_row.admin_message = message
        request_row.reviewed_by = actor
        request_row.reviewed_at = timezone.now()
        request_row.save(
            update_fields=[
                "status",
                "admin_message",
                "reviewed_by",
                "reviewed_at",
                "updated_at",
            ]
        )
        event = record_event(
            reservation,
            ReservationEvent.EventType.RESCHEDULE_INFO_REQUIRED,
            actor=actor,
            from_status=reservation.status,
            to_status=reservation.status,
            message=message,
        )
        notify(
            reservation.requester,
            Notification.Type.RESERVATION,
            "More information needed",
            f"GSO staff need more information about the reschedule request for "
            f"{reservation.event_name}: {message}",
            _reservation_link(reservation),
            event_key=f"reservation-event:{event.pk}:reschedule-info",
        )
        recipient = _email(reservation)
        if recipient:
            from notifications.email_service import send_reschedule_info_requested

            transaction.on_commit(
                lambda current=reservation, req=request_row, to=recipient: (
                    send_reschedule_info_requested(current, req, to)
                ),
                robust=True,
            )
    return request_row
