"""Automatic three-days-before reservation reminders.

Approved reservations are reminded once, three calendar days before the
scheduled event, through:

* the EXISTING in-app notification system
  (``notifications.models.Notification`` / ``notifications.services.notify``), and
* the EXISTING branded email pipeline
  (``notifications.email_service.send_reservation_reminder``).

There is no duplicate reminder model. Two delivery markers on the reservation
keep the channels independent and survive restarts:

* ``reminder_sent_at``       — in-app notification delivered,
* ``reminder_email_sent_at`` — reminder email accepted by the SMTP backend.

``reminder_email_claimed_at`` is a short-lived in-progress lease. It is written
*instead of* the sent marker while an SMTP send is happening, so two workers
can never email the same reservation, and it is cleared on failure (or expires
after a crash) so the send is retried on a later sweep. The sent timestamp is
only written after the email was successfully handed to the email backend.

Eligibility rules (all enforced here, never in the frontend):

* Only ``APPROVED`` reservations. Pending, rejected, cancelled, expired,
  active, completed, and already-no-show reservations never qualify.
* The event must not have started yet.
* The reminder becomes due three calendar days before the event date, or
  immediately when the reservation was approved inside that three-day window,
  as long as the event has not started.
* A reservation approved on or after its event date never receives a reminder.
* The requester must have a valid email address for the email channel. When
  there is no valid address the email is skipped safely (and logged); the
  in-app notification, when possible, is unaffected.
* A reservation cancelled (or otherwise made ineligible) before the sweep runs
  is skipped automatically because its status is re-checked at send time.

Delivery is idempotent and concurrency-safe. The in-app channel claims its
marker with a conditional ``UPDATE ... WHERE reminder_sent_at IS NULL AND
status = APPROVED``. The email channel claims ``reminder_email_claimed_at``
with a conditional update (also touching an expired claim from a crashed
worker), sends, then records success. A duplicate cron run, a retry after a
restart, or two overlapping workers therefore produce exactly one email and
one in-app notification.

Timezone: dates are stored as ``date`` + ``time`` and interpreted in Django's
configured timezone (``settings.TIME_ZONE``, Asia/Manila). ``timezone.localdate``
is used on every boundary so a reminder fires on the requester's local calendar
day even when the server stores UTC timestamps.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from notifications.email_service import (
    resolve_requester_email,
    send_reservation_reminder,
)
from notifications.models import Notification
from notifications.services import notify
from reservations.models import Reservation, ReservationEvent

logger = logging.getLogger(__name__)

#: Calendar days before the event the reminder is scheduled for.
REMINDER_DAYS = getattr(settings, "RESERVATION_REMINDER_DAYS", 3)

#: How long an in-progress email claim is valid before another sweep may retry.
EMAIL_CLAIM_TIMEOUT = timedelta(
    seconds=getattr(settings, "REMINDER_EMAIL_CLAIM_TIMEOUT_SECONDS", 900)
)

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
    it was approved on or after its event date. Otherwise the due date is the
    later of "three days before the event" and the approval date, which is what
    makes a late approval (inside the three-day window) due immediately.
    """
    approved_at = reservation.approved_at or reservation.created_at
    approved_on = timezone.localtime(approved_at).date()
    if approved_on >= reservation.date:
        return None
    return max(reservation.date - timedelta(days=REMINDER_DAYS), approved_on)


def _is_in_due_window(reservation: Reservation, now=None) -> bool:
    """Shared three-day-window/status rule for both delivery channels."""
    if reservation.status != Reservation.Status.APPROVED:
        return False
    current = now or timezone.now()
    # Never remind once the event has started (a reminder after the fact is
    # useless) or for a date that has already passed.
    if current >= reservation.start_datetime:
        return False
    due = reminder_due_date(reservation)
    if due is None:
        return False
    return timezone.localdate(current) >= due


def is_reminder_due(reservation: Reservation, now=None) -> bool:
    """Whether the in-app reminder should be delivered at ``now``."""
    return (
        reservation.reminder_sent_at is None
        and _is_in_due_window(reservation, now)
    )


def is_email_reminder_due(reservation: Reservation, now=None) -> bool:
    """Whether the reminder email should be delivered at ``now``."""
    return (
        reservation.reminder_email_sent_at is None
        and _is_in_due_window(reservation, now)
    )


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


def _send_in_app_reminder(reservation: Reservation, now) -> bool:
    """Claim and deliver the in-app reminder. Returns ``True`` when sent.

    The claim and notification are one transaction: a failed notification
    rolls back the ``reminder_sent_at`` write, leaving it eligible for retry.
    """
    if reservation.requester_id is None:
        # Staff-entered external reservations have no account, and the
        # existing in-app notification system delivers to accounts only.
        logger.info(
            "In-app reminder skipped for reservation %s: no requester account.",
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
            logger.info(
                "In-app reminder skipped for reservation %s: already sent or "
                "no longer eligible.",
                reservation.reservation_id,
            )
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


def _claim_email(reservation: Reservation, now) -> bool:
    """Atomically reserve the email send for this sweep.

    A claim is allowed when no email has been sent and either no send is in
    progress or the previous one crashed long enough ago that its lease expired.
    """
    cutoff = now - EMAIL_CLAIM_TIMEOUT
    claimed = (
        Reservation.objects.filter(
            pk=reservation.pk,
            status=Reservation.Status.APPROVED,
            reminder_email_sent_at__isnull=True,
        )
        .filter(
            Q(reminder_email_claimed_at__isnull=True)
            | Q(reminder_email_claimed_at__lt=cutoff)
        )
        .update(reminder_email_claimed_at=now)
    )
    return bool(claimed)


def _release_email_claim(reservation: Reservation, claimed_at) -> None:
    """Release a failed/incomplete claim so a later sweep retries it."""
    Reservation.objects.filter(
        pk=reservation.pk, reminder_email_claimed_at=claimed_at
    ).update(reminder_email_claimed_at=None)


def _send_email_reminder(reservation: Reservation, now) -> str:
    """Claim and deliver the reminder email.

    Returns ``"sent"``, ``"skipped"``, ``"no_email"`` or ``"failed"``. The
    ``reminder_email_sent_at`` marker is written only after the email backend
    accepts the message. Any failure releases the claim, so the next scheduled
    sweep retries it instead of losing the reminder.
    """
    if not resolve_requester_email(reservation):
        logger.warning(
            "Reminder email skipped for reservation %s: requester has no "
            "valid email address.",
            reservation.reservation_id,
        )
        return "no_email"

    if not _claim_email(reservation, now):
        logger.info(
            "Reminder email skipped for reservation %s: already sent or "
            "another worker is sending it.",
            reservation.reservation_id,
        )
        return "skipped"

    try:
        ok, reason = send_reservation_reminder(reservation)
    except Exception:  # noqa: BLE001 — one failed email must not stop the sweep
        ok, reason = False, "unexpected_error"
        logger.exception(
            "Unexpected error while sending reminder email for reservation %s.",
            reservation.reservation_id,
        )

    if not ok:
        _release_email_claim(reservation, now)
        logger.error(
            "Reminder email FAILED for reservation %s (reason: %s); it will be "
            "retried on the next check.",
            reservation.reservation_id,
            reason,
        )
        return "failed"

    Reservation.objects.filter(
        pk=reservation.pk, reminder_email_claimed_at=now
    ).update(reminder_email_sent_at=now, reminder_email_claimed_at=None)
    reservation.reminder_email_sent_at = now
    reservation.reminder_email_claimed_at = None
    logger.info(
        "Reminder email sent for reservation %s (%s) to the requester.",
        reservation.reservation_id,
        reservation.date,
    )
    return "sent"


def _process_reminder(reservation: Reservation, now) -> dict:
    """Deliver every still-pending channel for one reservation."""
    email_result = "not_due"
    in_app_result = "not_due"

    if is_email_reminder_due(reservation, now):
        email_result = _send_email_reminder(reservation, now)
    if is_reminder_due(reservation, now):
        in_app_result = "sent" if _send_in_app_reminder(reservation, now) else "skipped"

    return {
        "delivered": email_result == "sent" or in_app_result == "sent",
        "failed": email_result == "failed",
        "email_result": email_result,
        "in_app_result": in_app_result,
    }


def _send_reminder(reservation: Reservation, now) -> bool:
    """Backward-compatible single-reservation helper (True when delivered)."""
    return _process_reminder(reservation, now)["delivered"]


def send_due_reminders(now=None) -> dict:
    """Send every due reminder; returns a small summary for the command/logs.

    A failure for one reservation is logged and never stops the sweep. The
    failed channel is retried on the next scheduled run because its claim was
    released (email) or its transaction rolled back (in-app).
    """
    now = now or timezone.now()
    if timezone.is_naive(now):
        now = timezone.make_aware(now)
    today = timezone.localdate(now)
    last_day = today + timedelta(days=REMINDER_DAYS)

    logger.info(
        "Reservation reminder check started (window: %s through %s).",
        today,
        last_day,
    )

    candidates = list(
        Reservation.objects.select_related(
            "facility", "requester", "requester__organization_ref"
        )
        .prefetch_related("items__equipment")
        .filter(
            status=Reservation.Status.APPROVED,
            # Never look further ahead than the reminder window, and never at
            # past events. Late approvals inside the window are still found.
            date__gte=today,
            date__lte=last_day,
        )
        .filter(
            # At least one channel is still pending.
            Q(reminder_sent_at__isnull=True)
            | Q(reminder_email_sent_at__isnull=True)
        )
        .order_by("date", "start_time", "id")
    )

    already_sent = (
        Reservation.objects.filter(
            status=Reservation.Status.APPROVED,
            date__gte=today,
            date__lte=last_day,
            reminder_sent_at__isnull=False,
            reminder_email_sent_at__isnull=False,
        ).count()
    )
    logger.info(
        "Found %d reservation(s) with a pending reminder channel in the next "
        "%d day(s); %d already have both reminders recorded.",
        len(candidates),
        REMINDER_DAYS,
        already_sent,
    )

    sent = skipped = failed = 0
    emails_sent = emails_skipped = emails_failed = 0

    for reservation in candidates:
        if not (
            is_reminder_due(reservation, now)
            or is_email_reminder_due(reservation, now)
        ):
            skipped += 1
            continue
        try:
            result = _process_reminder(reservation, now)
        except Exception:  # noqa: BLE001 — one failure must not stop the sweep
            failed += 1
            logger.exception(
                "Failed to process reminder for reservation %s; it will be "
                "retried on the next run.",
                reservation.reservation_id,
            )
            continue

        if result["email_result"] == "sent":
            emails_sent += 1
        elif result["email_result"] == "failed":
            emails_failed += 1
            failed += 1
        elif result["email_result"] in ("skipped", "no_email"):
            emails_skipped += 1

        if result["delivered"]:
            sent += 1
        else:
            skipped += 1

    summary = {
        "scanned": len(candidates),
        "sent": sent,
        "skipped": skipped,
        "failed": failed,
        "already_sent": already_sent,
        "emails_sent": emails_sent,
        "emails_skipped": emails_skipped,
        "emails_failed": emails_failed,
    }
    logger.info(
        "Reservation reminder check finished: %(sent)d delivered, "
        "%(skipped)d skipped, %(failed)d failed (%(emails_sent)d email(s) "
        "sent, %(emails_failed)d email failure(s), %(already_sent)d already "
        "reminded)." % summary
    )
    return summary
