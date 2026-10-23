# -*- coding: utf-8 -*-
"""
Configurable check-in reminder window for SAS RESERVE.

Used by the reservation-notification sweep to decide when an approved,
not-yet-checked-in, not-yet-started reservation is due for its check-in
reminder email. The same reliable email pipeline and branding are reused
across all reservation notifications.
"""

from __future__ import annotations

from django.conf import settings
from django.utils import timezone

CHECKIN_REMINDER_MINUTES = int(
    getattr(settings, "CHECKIN_REMINDER_MINUTES_BEFORE_START", "30")
)


def _local_start(reservation):
    """Timezone-aware scheduled start in the project's local timezone."""
    start = reservation.start_datetime
    if start is None:
        return None
    if timezone.is_naive(start):
        start = timezone.make_aware(start)
    return timezone.localtime(start)


def reminder_window_for(reservation):
    """The timezone-aware window during which this reminder is due.

    Default policy: CHECKIN_REMINDER_MINUTES_BEFORE_START before the scheduled
    start time, until (but not including) the event starts. The sweep must
    re-check eligibility right before sending — this helper only computes the
    window, it does not change any reservation.
    """
    start = _local_start(reservation)
    if start is None:
        return None
    from_dt = start - timezone.timedelta(minutes=CHECKIN_REMINDER_MINUTES)
    until = start
    return timezone.make_aware(from_dt), until
