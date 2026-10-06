"""Automatic expiration of unapproved reservations.

A reservation that is still PENDING once its scheduled *event start time* is
reached was never approved in time. It is moved to the dedicated EXPIRED
status — deliberately distinct from REJECTED (an explicit staff decision) and
CANCELLED (withdrawn by a person) — and is never deleted: the record stays in
history and simply stops holding the facility/resources.

Expiration is enforced on the backend, not by a frontend timer. The check is
cheap and idempotent, so it is run before every reservation-facing read
(list / detail / dashboard / calendar / counts) and before the approval and
check-in operations. ``manage.py expire_reservations`` is provided for
schedulers (e.g. a Render cron job), but no paid infrastructure or always-on
background worker is required.

Time handling: dates are stored as a naive ``date`` + ``time`` in the
project's local time zone (``settings.TIME_ZONE``, Asia/Manila) and compared
against ``django.utils.timezone.now()`` after being made time-zone aware, so
the boundary is the requester's own wall clock — 7:59 AM is still Pending,
8:00 AM is Expired.
"""

from __future__ import annotations

import logging
from datetime import datetime

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from accounts.models import AuditLog
from reservations.models import Reservation, ReservationEvent

logger = logging.getLogger(__name__)

EXPIRATION_MESSAGE = (
    "Reservation expired because it was not approved before the scheduled "
    "event time."
)


def event_start(reservation: Reservation):
    """Time-zone-aware datetime the reservation's event begins."""
    return timezone.make_aware(
        datetime.combine(reservation.date, reservation.start_time)
    )


def is_overdue(reservation: Reservation, now=None) -> bool:
    """True once the scheduled EVENT START TIME has been reached.

    Only meaningful for the pending-decision window; callers decide whether the
    reservation's current status is eligible to expire.
    """
    if reservation.date is None or reservation.start_time is None:
        return False
    return (now or timezone.now()) >= event_start(reservation)


def expire_reservation(reservation: Reservation, *, now=None) -> bool:
    """Move one PENDING reservation to EXPIRED if its start time has passed.

    Only PENDING reservations ever transition: APPROVED / ACTIVE / COMPLETED /
    REJECTED / CANCELLED records are never touched. Returns ``True`` when this
    call performed the transition. Idempotent — a safe no-op on a reservation
    that is not pending or whose event has not started yet.
    """
    if reservation.status != Reservation.Status.PENDING:
        return False
    if not is_overdue(reservation, now=now):
        return False

    with transaction.atomic():
        # Re-read under a lock so a concurrent approval cannot be silently
        # overwritten by the expiry write (Postgres). SQLite ignores the lock,
        # where the guard below still prevents a double transition.
        locked = Reservation.objects.select_for_update().get(pk=reservation.pk)
        if locked.status != Reservation.Status.PENDING:
            return False
        locked.status = Reservation.Status.EXPIRED
        locked.save(update_fields=["status", "updated_at"])
        ReservationEvent.objects.create(
            reservation=locked,
            actor=None,
            event_type=ReservationEvent.EventType.EXPIRED,
            from_status=Reservation.Status.PENDING,
            to_status=Reservation.Status.EXPIRED,
            message=EXPIRATION_MESSAGE,
        )
        AuditLog.record(
            None,
            AuditLog.Action.RESERVATION_STATUS,
            object_type="reservation",
            object_id=locked.reservation_id,
            object_repr=locked.event_name,
            detail=f"Automatically expired — {EXPIRATION_MESSAGE}",
        )

    # Keep the caller's in-memory instance in sync with the write above.
    reservation.status = Reservation.Status.EXPIRED
    reservation.updated_at = locked.updated_at
    logger.info(
        "Reservation %s expired (event start %s).",
        reservation.reservation_id,
        event_start(reservation).isoformat(),
    )
    return True


def expire_overdue_reservations(queryset=None) -> int:
    """Expire every overdue PENDING reservation; returns the number expired.

    ``queryset`` optionally narrows the scan (used by tests); by default the
    whole table is synchronised, because expiration is a system-wide state, not
    a per-viewer one.
    """
    now = timezone.now()
    today = timezone.localdate(now)
    now_time = timezone.localtime(now).time()
    candidates = (queryset if queryset is not None else Reservation.objects.all()).filter(
        status=Reservation.Status.PENDING
    ).filter(Q(date__lt=today) | Q(date=today, start_time__lte=now_time))

    expired = 0
    for reservation in list(candidates.select_related("facility")):
        if expire_reservation(reservation, now=now):
            expired += 1
    if expired:
        logger.info("Expired %s overdue pending reservation(s).", expired)
    return expired


def refresh_reservation_status(reservation: Reservation, *, now=None) -> bool:
    """Expire a single reservation in place when it is overdue.

    Used right before approve / check-in so a stale PENDING can never be acted
    on. Returns ``True`` when the reservation was expired by this call.
    """
    return expire_reservation(reservation, now=now)
