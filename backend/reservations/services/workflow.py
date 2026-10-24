"""Reservation workflow actions and their notifications."""

from __future__ import annotations

import logging

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from accounts.models import AuditLog
from notifications.models import Notification
from notifications.services import notify, notify_staff
from notifications.email_service import (
    send_reservation_approved,
    send_reservation_cancelled,
    send_reservation_checkin_reminder,
    send_reservation_no_show_notice,
    send_reservation_notification,
    send_reservation_rejected,
    send_reservation_reminder,
    send_reservation_submitted,
    resolve_requester_email,
)
from reservations.models import InspectionReport, Reservation, ReservationEvent
from reservations.services import expiration

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


def _mask_email(email: str) -> str:
    """Mask a recipient address for logs — never log the full address."""
    local, _, domain = (email or "").partition("@")
    if not domain:
        return "invalid"
    return f"{local[:1]}***@{domain}"


def _send_approval_email_after_commit(reservation_id, actor, force=False):
    """Deliver and record an approval email after its approval transaction commits.

    ``force`` is set only by a genuine PENDING -> APPROVED transition: a
    reservation that was approved once, reopened through "request changes"
    and approved again must notify the requester again. Retry callers never
    force, so an already-delivered approval can never be sent twice.
    """
    logger.info(
        "Approval email on_commit callback EXECUTED for reservation id %s (force=%s).",
        reservation_id,
        force,
    )
    try:
        reservation = Reservation.objects.select_related(
            "requester", "facility", "created_by"
        ).get(pk=reservation_id)
        resend_approval_email(reservation, actor, force=force)
    except Exception as exc:  # Delivery bookkeeping must not undo an approval.
        logger.exception(
            "Approval email callback FAILED for reservation id %s (%s). "
            "The approval itself is already committed and remains unchanged.",
            reservation_id,
            type(exc).__name__,
        )
        # Never leave the diagnostic claiming delivery when it could not be
        # recorded. This is best-effort: if the database is also unavailable
        # the failure is logged and nothing is corrupted.
        try:
            Reservation.objects.filter(pk=reservation_id).update(
                approval_email_status=Reservation.ApprovalEmailStatus.FAILED
            )
            logger.info(
                "Approval email status persisted as FAILED for reservation id %s.",
                reservation_id,
            )
        except Exception:  # noqa: BLE001 - logging must not raise either
            logger.exception(
                "Could not persist FAILED approval-email status for reservation id %s.",
                reservation_id,
            )


def _schedule_approval_email(reservation, actor):
    """Queue exactly one delivery for a newly approved reservation."""
    logger.info(
        "Approval email scheduled after commit for reservation %s (status=%s).",
        reservation.reservation_id,
        reservation.status,
    )
    transaction.on_commit(
        lambda reservation_id=reservation.pk, actor=actor: (
            _send_approval_email_after_commit(reservation_id, actor, force=True)
        )
    )


def _schedule_approval_letter(reservation):
    """Queue the (idempotent) creation of the reservation's approval letter.

    Imported lazily: the letters app reads ``reservations.models``, so a module
    -level import here would be circular. The letters service is idempotent —
    a re-approval after a change request reuses the existing letter instead of
    creating a second one. Failures are contained inside the letters service
    and can never undo the committed approval.
    """
    from approval_letters.services import create_letter_after_commit

    logger.info(
        "Approval letter scheduled after commit for reservation %s (status=%s).",
        reservation.reservation_id,
        reservation.status,
    )
    transaction.on_commit(
        lambda reservation_id=reservation.pk: create_letter_after_commit(reservation_id)
    )


def resend_approval_email(reservation, actor, force=False) -> str:
    """Send an approval email once for an approved reservation, recording outcome.

    The row lock serialises concurrent attempts (a double-clicked retry or two
    administrators acting at once): the first attempt sends and persists the
    result, the next re-reads the committed SENT state and sends nothing.
    ``force`` is reserved for a new approval transition (see
    ``_send_approval_email_after_commit``); manual retries leave it False.
    """
    with transaction.atomic():
        # Lock ONLY the reservation row: ``requester`` is nullable, and
        # ``select_for_update`` on PostgreSQL refuses to lock the nullable
        # side of the outer join that ``select_related("requester")`` creates.
        locked = Reservation.objects.select_for_update().get(pk=reservation.pk)

        if locked.status != Reservation.Status.APPROVED:
            raise ValueError(
                "Only approved reservations can receive an approval email."
            )
        if (
            locked.approval_email_status == Reservation.ApprovalEmailStatus.SENT
            and not force
        ):
            logger.info(
                "Approval email already SENT for reservation %s; nothing sent.",
                locked.reservation_id,
            )
            status = locked.approval_email_status
        else:
            email = resolve_requester_email(locked, actor)
            if not email:
                locked.approval_email_status = Reservation.ApprovalEmailStatus.NO_EMAIL
                locked.save(update_fields=["approval_email_status", "updated_at"])
                logger.warning(
                    "Approval email skipped for reservation %s: requester has "
                    "no valid email address.",
                    locked.reservation_id,
                )
                status = locked.approval_email_status
            else:
                # Dispatch and record the delivery state. A failure must never
                # undo the approval: the transition has already committed.
                logger.info(
                    "Approval email attempt for reservation %s (recipient: %s).",
                    locked.reservation_id,
                    _mask_email(email),
                )
                try:
                    ok, reason = send_reservation_approved(locked, actor)
                except Exception as exc:  # noqa: BLE001 - never undo approval
                    ok, reason = False, type(exc).__name__
                    logger.exception(
                        "Approval email send raised for reservation %s (%s).",
                        locked.reservation_id,
                        type(exc).__name__,
                    )
                locked.approval_email_status = (
                    Reservation.ApprovalEmailStatus.SENT
                    if ok
                    else Reservation.ApprovalEmailStatus.FAILED
                )
                locked.save(update_fields=["approval_email_status", "updated_at"])
                status = locked.approval_email_status
                if ok:
                    logger.info(
                        "Approval email status persisted as SENT for reservation %s.",
                        locked.reservation_id,
                    )
                else:
                    logger.error(
                        "Approval email status persisted as FAILED for reservation "
                        "%s (reason: %s). The approval remains %s.",
                        locked.reservation_id,
                        reason,
                        locked.status,
                    )
    reservation.approval_email_status = status
    return status


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
    with transaction.atomic():
        locked = Reservation.objects.select_for_update().get(pk=reservation.pk)
        expiration.refresh_reservation_status(locked)
        if locked.status == Reservation.Status.EXPIRED:
            raise ValueError(
                "This reservation has expired and can no longer be approved."
            )
        from_status = locked.status
        locked.status = Reservation.Status.APPROVED
        locked.approved_by = actor
        locked.approved_at = timezone.now()
        locked.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
        record_event(
            locked,
            ReservationEvent.EventType.APPROVED,
            actor=actor,
            from_status=from_status,
            to_status=locked.status,
            message=message or "Automatically approved — created by an administrator.",
        )
        AuditLog.record(
            actor,
            AuditLog.Action.RESERVATION_APPROVED,
            object_type="reservation",
            object_id=locked.reservation_id,
            object_repr=locked.event_name,
            detail="Auto-approved (administrator-created reservation)",
        )
        notify(
            locked.requester,
            Notification.Type.RESERVATION,
            "Reservation approved",
            f"{locked.event_name} on {locked.date} was automatically approved.",
            _reservation_link(locked),
        )
        notify_staff(
            Notification.Type.RESERVATION,
            "Reservation approved",
            f"{locked.event_name} on {locked.date} was automatically approved.",
            _reservation_link(locked),
            exclude_user=actor,
        )
        if from_status != Reservation.Status.APPROVED:
            _schedule_approval_email(locked, actor)
        _schedule_approval_letter(locked)
    reservation.refresh_from_db()
    return reservation


def approve_reservation(reservation, actor, comment=""):
    with transaction.atomic():
        locked = Reservation.objects.select_for_update().get(pk=reservation.pk)
        # A stale PENDING record whose event has already started must never be approved.
        expiration.refresh_reservation_status(locked)
        if locked.status == Reservation.Status.EXPIRED:
            raise ValueError(
                "This reservation has expired and can no longer be approved."
            )
        from_status = locked.status
        if locked.status != Reservation.Status.PENDING:
            raise ValueError("Only pending reservations can be approved.")
        locked.status = Reservation.Status.APPROVED
        locked.approved_by = actor
        locked.approved_at = timezone.now()
        locked.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
        logger.info(
            "Approval transition for reservation %s: %s -> %s (actor id %s).",
            locked.reservation_id,
            from_status,
            locked.status,
            getattr(actor, "pk", None),
        )
        record_event(
            locked,
            ReservationEvent.EventType.APPROVED,
            actor=actor,
            from_status=from_status,
            to_status=locked.status,
            message=comment,
        )
        AuditLog.record(
            actor,
            AuditLog.Action.RESERVATION_APPROVED,
            object_type="reservation",
            object_id=locked.reservation_id,
            object_repr=locked.event_name,
            detail=comment,
        )
        notify(
            locked.requester,
            Notification.Type.RESERVATION,
            "Reservation approved",
            f"{locked.event_name} on {locked.date} has been approved.",
            _reservation_link(locked),
        )
        notify_staff(
            Notification.Type.RESERVATION,
            "Reservation approved",
            f"{locked.event_name} on {locked.date} was approved.",
            _reservation_link(locked),
            exclude_user=actor,
        )
        _schedule_approval_email(locked, actor)
        _schedule_approval_letter(locked)
    reservation.refresh_from_db()
    return reservation


def reject_reservation(reservation, actor, reason):
    # An expired reservation is already final; it must not be turned into a
    # rejection (the Pending → Expired and Pending → Rejected distinctions stay
    # visible).
    if reservation.status == Reservation.Status.EXPIRED:
        raise ValueError(
            "This reservation has expired and can no longer be rejected."
        )
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
    notify_staff(
        Notification.Type.RESERVATION,
        "Reservation rejected",
        f"{reservation.event_name} on {reservation.date} was rejected. Reason: {reason}",
        _reservation_link(reservation),
        exclude_user=actor,
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


def resubmit_reservation(reservation, actor, message=""):
    """Record the requester's revision of a reservation awaiting review.

    Called after the updated details (and resources) have been saved and
    revalidated. The status does NOT change: a resubmitted reservation is
    still PENDING, so it simply re-enters the administrators' review queue — it
    is never auto-approved. The administrator's original change request stays
    untouched in the timeline (events are append-only); this appends the
    revision entry and notifies staff so somebody picks it up.
    """
    if reservation.status != Reservation.Status.PENDING:
        raise ValueError(
            "Only a reservation that is awaiting review can be resubmitted."
        )
    default_message = (
        "Reservation updated and resubmitted."
        if actor.is_sas_staff
        else "Reservation updated and resubmitted by requester."
    )
    record_event(
        reservation,
        ReservationEvent.EventType.UPDATED,
        actor=actor,
        from_status=Reservation.Status.PENDING,
        to_status=Reservation.Status.PENDING,
        message=message or default_message,
    )
    AuditLog.record(
        actor,
        AuditLog.Action.RESERVATION_EDITED,
        object_type="reservation",
        object_id=reservation.reservation_id,
        object_repr=reservation.event_name,
        detail=message or default_message,
    )
    notify_staff(
        Notification.Type.RESERVATION,
        "Reservation resubmitted",
        (
            f"{reservation.event_name} on {reservation.date} "
            f"({reservation.start_time:%H:%M}–{reservation.end_time:%H:%M}) was "
            "revised and is awaiting approval again."
        ),
        _reservation_link(reservation),
    )
    return reservation


def request_changes(reservation, actor, message):
    # Requesting changes puts a reservation back to PENDING; doing that to an
    # expired reservation would silently reopen it. Those must be rebooked.
    if reservation.status == Reservation.Status.EXPIRED:
        raise ValueError(
            "This reservation has expired and can no longer be reopened. "
            "Request a new schedule instead."
        )
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
    notify_staff(
        Notification.Type.RESERVATION,
        "Changes requested",
        f"Changes were requested for {reservation.event_name}: {message}",
        _reservation_link(reservation),
        exclude_user=actor,
    )
    return reservation


def cancellation_eligibility(reservation, user):
    """Evaluate the cancellation policy for ``user`` against ``reservation``.

    Single source of truth for BOTH the API's ``can_cancel`` field (what the
    frontend displays) and the ``cancel`` endpoint's enforcement — the policy
    is never decided in React and never trusted from a client flag.

    Returns ``(can_cancel, code, reason)`` where ``code`` is:

    * ``""``                    — cancellable
    * ``"not_permitted"``       — the user is neither the requester nor staff
    * ``"status"``              — terminal status (COMPLETED / CANCELLED /
      REJECTED / EXPIRED / NO_SHOW can never be cancelled)
    * ``"event_ended"``         — the event's scheduled END time has already
      passed (refused for requesters and staff alike)
    * ``"cancellation_window"`` — requester (non-staff) cancelling a
      reservation whose event date is today or tomorrow
    """
    staff = bool(user is not None and getattr(user, "is_sas_staff", False))
    user_id = getattr(user, "id", None)
    is_owner = (
        user_id is not None
        and reservation.requester_id is not None
        and user_id == reservation.requester_id
    )
    if not (is_owner or staff):
        return False, "not_permitted", ""
    if reservation.status in Reservation.TERMINAL_STATUSES:
        return False, "status", "This reservation can no longer be cancelled."
    # An event whose scheduled END time has passed is history: it can no
    # longer be cancelled by anyone, staff included. From the day after the
    # event the administrator's Mark as No-Show decision is the only remaining
    # action, and a past event must never be pulled back into the live
    # workflow. Keyed off the scheduled end in the project's timezone
    # (``Reservation.has_ended``), never the creation date.
    if reservation.has_ended:
        return (
            False,
            "event_ended",
            (
                "This reservation's event has already ended and can no "
                "longer be cancelled."
            ),
        )
    # Cancellation-window policy: requesters cannot cancel a reservation whose
    # event date is today or tomorrow (even one created days in advance).
    # Staff/admin are exempt from THIS window (they are not exempt from the
    # event-ended rule above). Compared against the server's local calendar date
    # (Asia/Manila) using the event date, not the creation date. 2+ days out is
    # cancellable.
    if is_owner and not staff:
        days_until_event = (reservation.date - timezone.localdate()).days
        if 0 <= days_until_event <= 1:
            return (
                False,
                "cancellation_window",
                "Reservations scheduled within the next 2 days cannot be cancelled.",
            )
    return True, "", ""


def cancel_reservation(reservation, actor, reason=""):
    """Cancel a reservation (by its own requester or by SAS staff).

    Enforced via ``cancellation_eligibility``: terminal statuses (COMPLETED,
    CANCELLED, REJECTED, EXPIRED, NO_SHOW) can never be cancelled, an event
    that has already ended can never be cancelled (staff included), and a
    requester cannot cancel a reservation whose event date is today or
    tomorrow — staff are exempt from that window only.

    The whole transition runs in one transaction under a row lock, so the
    policy always revalidates the CURRENT database state: two rapid
    cancellation requests (double-click), or a status change made by an
    administrator in the same instant, produce exactly one transition and
    one set of timeline/audit/notification records — the losing request is
    rejected by the same policy (mirrors ``expire_reservation``).
    """
    is_requester = (
        reservation.requester_id is not None and actor.id == reservation.requester_id
    )
    with transaction.atomic():
        locked = Reservation.objects.select_for_update().get(pk=reservation.pk)
        can_cancel, code, blocker = cancellation_eligibility(locked, actor)
        if not can_cancel:
            if code == "cancellation_window":
                raise CancellationWindowError(blocker)
            raise ValueError(
                blocker or "You do not have permission to cancel this reservation."
            )
        from_status = locked.status
        locked.status = Reservation.Status.CANCELLED
        locked.save(update_fields=["status", "updated_at"])
        record_event(
            locked,
            ReservationEvent.EventType.CANCELLED,
            actor=actor,
            from_status=from_status,
            to_status=locked.status,
            message=reason or "Cancelled",
        )
        AuditLog.record(
            actor,
            AuditLog.Action.RESERVATION_CANCELLED,
            object_type="reservation",
            object_id=locked.reservation_id,
            object_repr=locked.event_name,
            detail=reason or "Cancelled",
        )
        if is_requester:
            notify_staff(
                Notification.Type.RESERVATION,
                "Reservation cancelled",
                f"{locked.event_name} on {locked.date} was cancelled by the requester.",
                _reservation_link(locked),
            )
        else:
            notify(
                locked.requester,
                Notification.Type.RESERVATION,
                "Reservation cancelled",
                f"{locked.event_name} on {locked.date} was cancelled.",
                _reservation_link(locked),
            )
            notify_staff(
                Notification.Type.RESERVATION,
                "Reservation cancelled",
                f"{locked.event_name} on {locked.date} was cancelled by SAS staff.",
                _reservation_link(locked),
                exclude_user=actor,
            )
    # Keep the caller's in-memory instance in sync with the persisted write,
    # so the API layer serializes the cancelled state it just recorded.
    reservation.status = locked.status
    reservation.updated_at = locked.updated_at
    # Send email notification — best-effort, outside the row lock; never raises.
    cancelled_by = "you" if is_requester else actor.display_name
    _send_reservation_email(
        reservation,
        status="CANCELLED",
        status_label="Cancelled",
        message=f"Your reservation was cancelled by {cancelled_by}.",
        next_action="Contact the SAS Office if you need to reschedule.",
    )
    return reservation


def no_show_eligibility(reservation, user=None, now=None):
    """Evaluate whether a reservation may be marked as a no-show.

    Single source of truth for BOTH the API's ``can_mark_no_show`` field (what
    the frontend displays) and the ``mark_no_show`` endpoint's enforcement, so
    the two can never disagree. Returns ``(allowed, code, reason)`` where
    ``code`` is ``""`` when allowed, or one of ``"not_permitted"``,
    ``"status"``, ``"checked_in"``, ``"already_marked"``,
    ``"date_not_passed"``.

    Rules: only SAS staff may perform the action; only an APPROVED reservation
    that was never checked in is eligible (an ACTIVE/COMPLETED one was
    attended); and the reservation's CALENDAR DATE must be at least one day in
    the past, in the project's configured timezone. Eligibility therefore
    begins at local midnight on the day AFTER the event — deliberately NOT 24
    hours after the scheduled start time (a reservation dated Oct 19 becomes
    eligible on Oct 20 regardless of its start time). Cancelled, rejected,
    expired, completed, and already-marked reservations are never eligible.
    """
    if user is not None and not getattr(user, "is_sas_staff", False):
        return False, "not_permitted", ""
    if reservation.status == Reservation.Status.NO_SHOW:
        return (
            False,
            "already_marked",
            "This reservation has already been marked as a no-show.",
        )
    if reservation.status != Reservation.Status.APPROVED:
        return (
            False,
            "status",
            "Only approved reservations can be marked as a no-show.",
        )
    if reservation.checked_in_at is not None:
        return (
            False,
            "checked_in",
            "This reservation was checked in and cannot be marked as a no-show.",
        )
    if timezone.localdate(now or timezone.now()) <= reservation.date:
        return (
            False,
            "date_not_passed",
            (
                "This reservation can only be marked as a no-show on or "
                "after the day following the scheduled event date."
            ),
        )
    return True, "", ""


def mark_no_show(reservation, actor, now=None):
    """Explicitly mark a past-date, approved reservation as a no-show.

    Administrator-only and never automatic: the caller must confirm the
    action. The status re-check, write, timeline entry, and audit record run in
    one transaction under a row lock, so a repeated or concurrent request —
    including a concurrent check-in — produces exactly one transition (the
    loser gets a clear error), and the original schedule remains available in
    the event/audit history.

    The requester IS notified with the same reliable email pipeline used for
    approval, reminders, and booking confirmations. The email is dispatched via
    ``transaction.on_commit`` so it only runs after the no-show transition has
    actually committed, and a failure is logged without undoing the status change.
    """
    if not getattr(actor, "is_sas_staff", False):
        raise PermissionDenied(
            "Only administrators can mark a reservation as a no-show."
        )
    now = now or timezone.now()

    with transaction.atomic():
        locked = Reservation.objects.select_for_update().get(pk=reservation.pk)
        allowed, code, blocker = no_show_eligibility(locked, actor, now=now)
        if not allowed:
            raise ValueError(
                blocker or "This reservation cannot be marked as a no-show."
            )

        marked_at = now
        from_status = locked.status
        locked.status = Reservation.Status.NO_SHOW
        locked.no_show_marked_at = marked_at
        locked.no_show_marked_by = actor
        locked.save(
            update_fields=[
                "status",
                "no_show_marked_at",
                "no_show_marked_by",
                "updated_at",
            ]
        )
        detail = (
            f"Marked as no-show by {actor.display_name} for "
            f"{locked.event_name}: the requester did not check in within the "
            f"permitted period. Scheduled event: {locked.date} "
            f"{locked.start_time:%H:%M}–{locked.end_time:%H:%M} at "
            f"{locked.facility.name}."
        )
        record_event(
            locked,
            ReservationEvent.EventType.NO_SHOW,
            actor=actor,
            from_status=from_status,
            to_status=locked.status,
            message=detail,
        )
        AuditLog.record(
            actor,
            AuditLog.Action.RESERVATION_NO_SHOW,
            object_type="reservation",
            object_id=locked.reservation_id,
            object_repr=locked.event_name,
            detail=detail,
        )

        # Notify the requester once the transition has committed. A delivery
        # failure is logged and retried later; it never undoes the no-show.
        transaction.on_commit(
            lambda: _send_no_show_notice_after_commit(locked, actor)
        )

    # Keep the caller's in-memory instance in sync with the persisted write.
    reservation.status = locked.status
    reservation.no_show_marked_at = locked.no_show_marked_at
    reservation.no_show_marked_by = locked.no_show_marked_by
    reservation.updated_at = locked.updated_at
    return reservation


def check_in_reservation(reservation, actor, override=False):
    """Check a reservation in.

    The check-in window opens 3 hours before the event start. Anyone may check
    in once the window is open. Before it opens, only an administrator who
    explicitly confirms the override (``override=True``) is allowed — the
    backend verifies the role itself; a regular user cannot bypass the window
    by sending the flag.
    """
    now = timezone.now()
    with transaction.atomic():
        locked = Reservation.objects.select_for_update().get(pk=reservation.pk)
        # A stale PENDING whose event started is expired first, and an expired
        # reservation can never be checked in or occupy the facility.
        expiration.refresh_reservation_status(locked, now=now)
        if locked.status == Reservation.Status.EXPIRED:
            raise ValueError(
                "This reservation has expired and can no longer be checked in."
            )
        if locked.status == Reservation.Status.NO_SHOW:
            raise ValueError(
                "This reservation was marked as a no-show and cannot be checked in."
            )
        if locked.status == Reservation.Status.CANCELLED:
            raise ValueError(
                "This reservation was cancelled and cannot be checked in."
            )
        if locked.status not in (
            Reservation.Status.APPROVED,
            Reservation.Status.ACTIVE,
        ):
            raise ValueError("Only approved reservations can be checked in.")
        # One-day no-show rule: from the day AFTER the event date onward, the
        # reservation is in the administrator no-show window, so check-in is
        # closed even if it was never used. The API can never bypass this.
        if timezone.localdate(now) > locked.date:
            raise ValueError(
                "Check-in is no longer available: the reservation date has passed."
            )
        override_used = bool(
            now < locked.check_in_open_time and actor.is_admin and override
        )
        if now < locked.check_in_open_time and not override_used:
            raise CheckInNotOpenError(locked)
        from_status = locked.status
        locked.status = Reservation.Status.ACTIVE
        locked.checked_in_at = now
        locked.early_check_in_override = override_used
        locked.save(
            update_fields=[
                "status",
                "checked_in_at",
                "early_check_in_override",
                "updated_at",
            ]
        )
        record_event(
            locked,
            ReservationEvent.EventType.CHECKED_IN,
            actor=actor,
            from_status=from_status,
            to_status=locked.status,
            message=(
                "Early check-in override performed by an administrator before "
                "the standard 3-hour window."
                if override_used
                else "Requester checked in with SAS staff."
            ),
        )
        AuditLog.record(
            actor,
            AuditLog.Action.EARLY_CHECK_IN
            if override_used
            else AuditLog.Action.CHECK_IN,
            object_type="reservation",
            object_id=locked.reservation_id,
            object_repr=locked.event_name,
            detail=(
                f"Early check-in override — standard window opened at "
                f"{locked.check_in_open_time:%Y-%m-%d %H:%M}."
                if override_used
                else ""
            ),
        )

    # Keep the caller's in-memory instance in sync with the persisted write, so
    # the API layer serializes the checked-in state it just recorded.
    reservation.status = locked.status
    reservation.checked_in_at = locked.checked_in_at
    reservation.early_check_in_override = locked.early_check_in_override
    reservation.updated_at = locked.updated_at
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


def _send_no_show_notice_after_commit(reservation, actor):
    """Send the no-show notice after the no-show transition has committed.

    This runs via ``transaction.on_commit`` from ``mark_no_show`` so the email
    is only dispatched when the database write has actually succeeded. A
    delivery failure is logged and never raises back into the committing
    transaction.
    """
    ok, reason = send_reservation_no_show_notice(reservation, actor)
    if ok:
        logger.info(
            "No-show notice email recorded as sent for reservation %s.",
            reservation.reservation_id,
        )
    else:
        logger.error(
            "No-show notice email delivery FAILED for reservation %s (reason: %s). "
            "The no-show transition has already committed.",
            reservation.reservation_id,
            reason,
        )
