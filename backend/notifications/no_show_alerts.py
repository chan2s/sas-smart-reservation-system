"""Administrator warnings for reservations that look unattended.

The flow these alerts feed is::

    reservation data -> eligibility/stage calculation -> persisted alert
    -> staff-only API -> notification bell + dashboard

Nothing here changes a reservation's status. A reservation only becomes an
official NO_SHOW when an administrator explicitly marks it (see
``reservations.services.workflow.mark_no_show``); these rows are review prompts.

Two review sources feed the dashboard, always kept separate:

* active alerts — reservations inside the warning window (described below);
* :func:`awaiting_review` — APPROVED reservations whose scheduled end time has
  already passed and that were never checked in, completed, cancelled, or
  marked no-show. They are listed exactly as they are; nothing is marked
  automatically.

Eligibility (all evaluated in the project's configured timezone):

* status is ``APPROVED`` — pending requests, expired requests, cancelled,
  rejected, completed, active (already checked in) and no-show reservations are
  never eligible;
* no check-in has been recorded (``checked_in_at is None``) — absence of a
  check-in is shown as "No check-in recorded", never as proof of absence;
* the event has not ended yet (after ``end_datetime`` the explicit no-show
  process takes over, and the warning would be noise).

Stages, relative to the scheduled start time:

========================  =====================================================
``UPCOMING``              starts within 15 minutes, no check-in
``START_REACHED``         start time reached, still no check-in
``NO_SHOW_RISK``          15+ minutes past start, still no check-in
========================  =====================================================

Idempotency: one row per reservation (unique), updated in place. A repeated
sweep never inserts a second alert, and an alert is resolved as soon as the
reservation stops being eligible.

Times are computed with ``zoneinfo``/Django's ``timezone`` helpers from
``settings.TIME_ZONE`` (Asia/Manila), so a server running in UTC still opens the
window at the requester's local time.
"""

from __future__ import annotations

import logging
import math
from datetime import timedelta

from django.db import IntegrityError
from django.db.models import Case, IntegerField, Q, Value, When
from django.utils import timezone

from notifications.models import PossibleNoShowAlert
from reservations.models import Reservation

logger = logging.getLogger(__name__)

#: How long before the start time the first warning appears.
WARNING_WINDOW_MINUTES = 15

#: How long after the start time the alert escalates to "action required".
NO_SHOW_AFTER_MINUTES = 15

STAGE_ORDER = PossibleNoShowAlert.STAGE_ORDER


def _aware(now=None):
    """Return ``now`` as a timezone-aware datetime (defaults to right now)."""
    value = now or timezone.now()
    if timezone.is_naive(value):
        value = timezone.make_aware(value)
    return value


def is_eligible(reservation: Reservation, now=None) -> bool:
    """Whether ``reservation`` may carry an active possible-no-show alert."""
    current = _aware(now)
    if reservation.status != Reservation.Status.APPROVED:
        return False
    if reservation.checked_in_at is not None:
        return False
    if current >= reservation.end_datetime:
        return False
    warning_opens = reservation.start_datetime - timedelta(minutes=WARNING_WINDOW_MINUTES)
    return current >= warning_opens


def stage_for(reservation: Reservation, now=None) -> str | None:
    """The alert stage for ``reservation`` at ``now``; ``None`` when not due."""
    if not is_eligible(reservation, now):
        return None
    current = _aware(now)
    start = reservation.start_datetime
    if current < start:
        return PossibleNoShowAlert.Stage.UPCOMING
    if current < start + timedelta(minutes=NO_SHOW_AFTER_MINUTES):
        return PossibleNoShowAlert.Stage.START_REACHED
    return PossibleNoShowAlert.Stage.NO_SHOW_RISK


def _resolution_reason(reservation: Reservation) -> str:
    """Human explanation for why an alert stopped applying."""
    if reservation.checked_in_at is not None:
        return "The requester checked in."
    if reservation.status == Reservation.Status.ACTIVE:
        return "The reservation became active."
    if reservation.status == Reservation.Status.COMPLETED:
        return "The reservation was completed."
    if reservation.status == Reservation.Status.CANCELLED:
        return "The reservation was cancelled."
    if reservation.status == Reservation.Status.REJECTED:
        return "The reservation was rejected."
    if reservation.status == Reservation.Status.EXPIRED:
        return "The reservation expired."
    if reservation.status == Reservation.Status.NO_SHOW:
        return "The reservation was marked as a no-show."
    if reservation.status == Reservation.Status.PENDING:
        return "The reservation is waiting for approval again."
    return "The event ended."


def _open_or_create(reservation: Reservation, stage: str, now):
    """Return ``(alert, created)`` for ``reservation``, tolerating a race."""
    try:
        return (
            PossibleNoShowAlert.objects.get_or_create(
                reservation=reservation,
                defaults={
                    "stage": stage,
                    "detected_at": now,
                    "stage_changed_at": now,
                },
            )
        )
    except IntegrityError:
        # A concurrent sweep created the row between the SELECT and INSERT.
        return PossibleNoShowAlert.objects.get(reservation=reservation), False


def refresh_alerts(now=None) -> dict:
    """Create/update active alerts and resolve the ones that no longer apply.

    Safe to call as often as needed: only today's APPROVED, not-checked-in
    reservations are scanned (in practice a handful of rows), and every write is
    an in-place update of the reservation's single alert row.
    """
    current = _aware(now)
    today = timezone.localdate(current)

    candidates = (
        Reservation.objects.filter(
            status=Reservation.Status.APPROVED,
            checked_in_at__isnull=True,
            date=today,
        )
        .select_related("facility", "requester")
        .order_by("start_time", "id")
    )

    created = updated = escalated = 0
    active_ids: list[int] = []

    for reservation in candidates:
        stage = stage_for(reservation, current)
        if stage is None:
            continue

        alert, was_created = _open_or_create(reservation, stage, current)
        if was_created:
            created += 1
        else:
            changed_fields = []
            if alert.resolved_at is not None:
                # The reservation became eligible again (e.g. a re-approval).
                alert.resolved_at = None
                alert.resolved_reason = ""
                changed_fields += ["resolved_at", "resolved_reason"]
            if alert.stage != stage:
                if STAGE_ORDER[stage] > STAGE_ORDER[alert.stage]:
                    # A more urgent state must not stay "read".
                    alert.acknowledged_at = None
                    alert.acknowledged_by = None
                    escalated += 1
                    changed_fields += ["acknowledged_at", "acknowledged_by"]
                alert.stage = stage
                alert.stage_changed_at = current
                changed_fields += ["stage", "stage_changed_at"]
            if changed_fields:
                alert.save(update_fields=changed_fields + ["updated_at"])
                updated += 1
        active_ids.append(reservation.pk)

    resolved = 0
    stale = (
        PossibleNoShowAlert.objects.filter(resolved_at__isnull=True)
        .exclude(reservation_id__in=active_ids)
        .select_related("reservation")
    )
    for alert in stale:
        alert.resolved_at = current
        alert.resolved_reason = _resolution_reason(alert.reservation)
        alert.save(update_fields=["resolved_at", "resolved_reason", "updated_at"])
        resolved += 1

    summary = {
        "scanned": len(active_ids) + resolved,
        "active": len(active_ids),
        "created": created,
        "updated": updated,
        "escalated": escalated,
        "resolved": resolved,
    }
    if created or updated or resolved:
        logger.info(
            "Possible no-show sweep: %(active)d active, %(created)d created, "
            "%(updated)d updated (%(escalated)d escalated), %(resolved)d "
            "resolved." % summary
        )
    return summary


def active_alerts():
    """Unresolved alerts, most urgent first, with their reservation details.

    ``NO_SHOW_RISK`` sorts before ``START_REACHED`` before ``UPCOMING``; within a
    stage the earlier reservation comes first.
    """
    urgency = Case(
        When(stage=PossibleNoShowAlert.Stage.NO_SHOW_RISK, then=Value(0)),
        When(stage=PossibleNoShowAlert.Stage.START_REACHED, then=Value(1)),
        default=Value(2),
        output_field=IntegerField(),
    )
    return (
        PossibleNoShowAlert.objects.filter(resolved_at__isnull=True)
        .select_related("reservation", "reservation__facility", "reservation__requester")
        .annotate(_urgency=urgency)
        .order_by("_urgency", "reservation__date", "reservation__start_time", "id")
    )


def awaiting_review(now=None):
    """Overdue APPROVED reservations that still need an explicit no-show review.

    These are the rows the alert sweep deliberately stops tracking once the
    event has ended: the scheduled end date/time is in the past, nobody checked
    in or out, and the reservation was never cancelled, completed, or marked
    ``NO_SHOW``. Nothing here changes a status — the administrator decides, via
    the existing ``workflow.mark_no_show`` action.

    The end boundary is computed in the project's configured timezone
    (``settings.TIME_ZONE``), so "today, 12:00" means local noon rather than
    UTC. Reservations that already have an ACTIVE possible-no-show alert are
    excluded so the dashboard never lists the same reservation twice.
    """
    current = _aware(now)
    local_now = timezone.localtime(current)
    today = local_now.date()
    active_alert_reservation_ids = PossibleNoShowAlert.objects.filter(
        resolved_at__isnull=True
    ).values("reservation_id")

    return (
        Reservation.objects.filter(
            status=Reservation.Status.APPROVED,
            checked_in_at__isnull=True,
            checked_out_at__isnull=True,
        )
        .filter(
            # Scheduled END time passed: earlier days entirely, or today once
            # the local end time is behind the clock.
            Q(date__lt=today) | Q(date=today, end_time__lt=local_now.time())
        )
        .exclude(pk__in=active_alert_reservation_ids)
        .select_related("facility", "requester")
        .order_by("date", "start_time", "id")
    )


def review_timing(reservation: Reservation, now=None) -> dict:
    """How long ago the reservation's scheduled end time passed."""
    current = _aware(now)
    seconds = (current - reservation.end_datetime).total_seconds()
    minutes = max(0, int(seconds // 60))

    if minutes < 1:
        label = "Ended just now"
    elif minutes < 60:
        label = f"Ended {minutes} minute{'s' if minutes != 1 else ''} ago"
    elif minutes < 24 * 60:
        hours = minutes // 60
        label = f"Ended {hours} hour{'s' if hours != 1 else ''} ago"
    else:
        days = minutes // (24 * 60)
        label = f"Ended {days} day{'s' if days != 1 else ''} ago"
    return {"minutes_since_end": minutes, "time_label": label}


def acknowledge(alert: PossibleNoShowAlert, actor, now=None) -> PossibleNoShowAlert:
    """Mark one active alert as read (acknowledgement, not resolution)."""
    if alert.resolved_at is not None:
        raise ValueError("This alert is no longer active.")
    current = _aware(now)
    alert.acknowledged_at = current
    alert.acknowledged_by = actor if getattr(actor, "pk", None) else None
    alert.save(update_fields=["acknowledged_at", "acknowledged_by", "updated_at"])
    return alert


def acknowledge_all(actor, now=None) -> int:
    """Acknowledge every currently active alert. Returns the number updated."""
    current = _aware(now)
    return PossibleNoShowAlert.objects.filter(
        resolved_at__isnull=True, acknowledged_at__isnull=True
    ).update(
        acknowledged_at=current,
        acknowledged_by=actor if getattr(actor, "pk", None) else None,
        updated_at=current,
    )


def unread_count() -> int:
    """Active, unacknowledged alerts — the administrator part of the badge."""
    return PossibleNoShowAlert.objects.filter(
        resolved_at__isnull=True, acknowledged_at__isnull=True
    ).count()


def timing(reservation: Reservation, now=None) -> dict:
    """Minutes until/since the start plus a ready-to-render sentence."""
    current = _aware(now)
    start = reservation.start_datetime
    seconds = (start - current).total_seconds()

    if seconds > 0:
        minutes = max(1, math.ceil(seconds / 60))
        label = "Starts in 1 minute" if minutes == 1 else f"Starts in {minutes} minutes"
        return {
            "minutes_until_start": minutes,
            "minutes_since_start": None,
            "time_label": label,
            "no_check_in_label": "No check-in recorded",
        }

    minutes = max(0, int((-seconds) // 60))
    label = "Start time just passed" if minutes == 0 else f"Started {minutes} minutes ago"
    return {
        "minutes_until_start": None,
        "minutes_since_start": minutes,
        "time_label": label,
        "no_check_in_label": "No check-in recorded",
    }
