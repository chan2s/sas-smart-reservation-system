"""Automatic three-days-before reservation reminders.

Approved reservations are reminded once, three calendar days before the
scheduled event, through the EXISTING in-app notification system
(``notifications.models.Notification`` / ``notifications.services.notify``).
There is no separate reminder model or email pipeline: ``reminder_sent_at`` on
the reservation is the single delivery marker.

Eligibility rules (all enforced here, never in the frontend):

* Only ``APPROVED`` reservations. Pending, rejected, cancelled, expired,
  active, completed, and already-no-show reservations never qualify.
* The reminder becomes due three calendar days before the event date, or
  immediately when the reservation was approved inside that three-day window
  (requirement: approved late → remind promptly), as long as the event has not
  started.
* A reservation approved on or after its event date never receives a reminder.
* A reservation cancelled (or otherwise made ineligible) before the sweep runs
  is skipped automatically because its status is re-checked at send time.

Delivery is idempotent and concurrency-safe. Each candidate is claimed with a
conditional ``UPDATE ... WHERE reminder_sent_at IS NULL AND status = APPROVED``
inside a transaction; only the worker whose update affects a row creates the
notification. A duplicate cron run, a retry after a restart, or two overlapping
workers therefore produce exactly one notification. If the notification write
fails, the transaction rolls back the claim and the next run retries.

The sweep is exposed as ``manage.py send_reservation_reminders`` so the
existing cron-style scheduler (see ``expire_reservations``) can run it without
any always-on worker. It is safe to run as often as desired, e.g. hourly.

Timezone: dates are stored as ``date`` + ``time`` and interpreted in Django's
configured timezone (``settings.TIME_ZONE``, Asia/Manila). ``timezone.localdate``
is used on every boundary so a reminder fires on the requester's local calendar
day even when the server stores UTC timestamps.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from notifications.models import Notification
from notifications.services import notify
from reservations.models import Reservation, ReservationEvent

logger = logging.getLogger(__name__)

#: Calendar days before the event the reminder is scheduled for.
REMINDER_DAYS = 3

REMINDER_TITLE = "Upcoming Reservation Reminder"


def _format_event_date(value) -> str:
    """Human date without a leading zero (e.g. ``October 21, 2026``)."""
    return f"{value:%B} {value.day}, {value.year}"


def _format_time(value) -> str:
    """12-hour clock without a leading zero (e.g. ``9:00 AM``)."""
    return value.strftime("%I:%M %p").lstrip("0")


def reminder_due_date(reservation: Reservation):
    """First calendar day this reservation's reminder may be sent.

    Returns ``None`` when the reservation can never receive a reminder because
    it was approved on or after the event date. Otherwise the due date is the
    later of "three days before the event" and the approval date, which is what
    makes a late approval (inside the three-day window) due immediately.
    """
    approved_at = reservation.approved_at or reservation.created_at
    approved_on = timezone.localtime(approved_at).date()
    if approved_on >= reservation.date:
        return None
    return max(reservation.date - timedelta(days=REMINDER_DAYS), approved_on)


def is_reminder_due(reservation: Reservation, now=None) -> bool:
    """Whether ``reservation`` should receive its reminder at ``now``."""
    if reservation.status != Reservation.Status.APPROVED:
        return False
    if reservation.reminder_sent_at is not None:
        return False
    # Never remind once the event has started (a reminder after the fact is
    # useless) or for a date that has already passed.
    if (now or timezone.now()) >= reservation.start_datetime:
        return False
    due = reminder_due_date(reservation)
    if due is None:
        return False
    return timezone.localdate(now) >= due


def build_reminder_message(reservation: Reservation) -> str:
    """The notification body shown in the requester's notification list."""
    return (
        f"Your reservation {reservation.reservation_id} for "
        f"{reservation.event_name} at {reservation.facility.name} is scheduled "
        f"for {_format_event_date(reservation.date)} from "
        f"{_format_time(reservation.start_time)} to "
        f"{_format_time(reservation.end_time)}. Please remember to attend your "
        "scheduled reservation."
    )


def _send_reminder(reservation: Reservation, now) -> bool:
    """Claim and deliver one reminder. Returns ``True`` when it was sent.

    The claim and the notification are one transaction: a failed notification
    rolls back the ``reminder_sent_at`` write, leaving the reminder eligible
    for the next retry instead of silently losing it.
    """
    if reservation.requester_id is None:
        # Staff-entered external reservations have no account, and the
        # existing notification system delivers in-app notifications only.
        logger.info(
            "Reminder skipped for reservation %s: no requester account.",
            reservation.reservation_id,
        )
        return False

    with transaction.atomic():
        claimed = Reservation.objects.filter(
            pk=reservation.pk,
            status=Reservation.Status.APPROVED,
            reminder_sent_at__isnull=True,
        ).update(reminder_sent_at=now, updated_at=now)
        if not claimed:
            # Another worker (or an earlier run) already sent it, or the
            # reservation changed status between the scan and the claim.
            return False

        notify(
            reservation.requester,
            Notification.Type.RESERVATION,
            REMINDER_TITLE,
            build_reminder_message(reservation),
            f"/reservations/{reservation.id}",
        )
        ReservationEvent.objects.create(
            reservation=reservation,
            actor=None,
            event_type=ReservationEvent.EventType.REMINDER_SENT,
            from_status=Reservation.Status.APPROVED,
            to_status=Reservation.Status.APPROVED,
            message=(
                f"Automatic reminder sent to the requester "
                f"({REMINDER_DAYS} days before the event)."
            ),
        )

    # Keep the caller's instance in sync with the persisted write.
    reservation.reminder_sent_at = now
    reservation.updated_at = now
    return True


def send_due_reminders(now=None) -> dict:
    """Send every due reminder; returns a small summary for the command/logs.

    A failure for one reservation is logged and never stops the sweep. The
    reminder is retried on the next scheduled run because its
    ``reminder_sent_at`` claim was rolled back.
    """
    now = now or timezone.now()
    today = timezone.localdate(now)

    candidates = (
        Reservation.objects.select_related("facility", "requester")
        .filter(
            status=Reservation.Status.APPROVED,
            reminder_sent_at__isnull=True,
            # Never look further ahead than the reminder window, and never at
            # past events. Late approvals inside the window are still found.
            date__gte=today,
            date__lte=today + timedelta(days=REMINDER_DAYS),
        )
        .order_by("date", "start_time", "id")
    )

    sent = skipped = failed = 0
    for reservation in candidates:
        if not is_reminder_due(reservation, now):
            skipped += 1
            continue
        try:
            if _send_reminder(reservation, now):
                sent += 1
                logger.info(
                    "Reminder sent for reservation %s (%s).",
                    reservation.reservation_id,
                    reservation.date,
                )
            else:
                skipped += 1
        except Exception:  # noqa: BLE001 — one failure must not stop the sweep
            failed += 1
            logger.exception(
                "Failed to send reminder for reservation %s; it will be "
                "retried on the next run.",
                reservation.reservation_id,
            )

    return {
        "scanned": sent + skipped + failed,
        "sent": sent,
        "skipped": skipped,
        "failed": failed,
    }
