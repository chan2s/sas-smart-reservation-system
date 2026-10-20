"""Automatic booking-confirmation email for newly created reservations.

The confirmation is triggered by a SUCCESSFUL reservation creation on the
backend — never by the React frontend, and never by merely opening the booking
page. It reuses the project's existing email pipeline
(``notifications.email_service`` and the Gmail SMTP settings from ``.env``);
no second email configuration and no duplicate reservation model is added.

Delivery rules:

* The email is scheduled with ``transaction.on_commit`` so it only runs after
  the reservation (and its items/fees) has actually been committed. A failed
  or rolled-back creation therefore never sends one.
* The wording is derived from the reservation's SAVED status: a PENDING
  reservation is described as awaiting administrator approval; an
  administrator-created reservation that was auto-approved is described as
  approved. This module never changes the status or the approval rules.
* ``confirmation_email_sent_at`` is written only after the email backend
  accepts the message, so a failed send is never recorded as delivered.
  ``confirmation_email_claimed_at`` is a short-lived lease claimed with a
  conditional UPDATE, so a repeated request, a retry, or two workers can never
  email the same reservation twice.
* A failure is logged with a safe category only (no credentials, no SMTP
  password) and never propagates: the reservation stays saved and the API
  still returns its normal 201 response.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from notifications.email_service import send_booking_confirmation
from reservations.models import Reservation

logger = logging.getLogger(__name__)

#: How long an in-progress send may hold the claim before another attempt may
#: take it over (e.g. after a worker crash).
CLAIM_TIMEOUT = timedelta(minutes=15)


def schedule_booking_confirmation(reservation: Reservation) -> None:
    """Send the confirmation once, after the creation transaction commits.

    Call this after the reservation's final status has been decided (pending or
    auto-approved) so the email always reflects the status that was saved.
    """
    reservation_pk = reservation.pk
    if reservation_pk is None:
        return
    transaction.on_commit(
        lambda: deliver_booking_confirmation(reservation_pk)
    )


def deliver_booking_confirmation(reservation_pk: int) -> bool:
    """Deliver the booking confirmation for one reservation, at most once.

    Returns ``True`` only when the email was accepted by the email backend.
    Every outcome is logged; nothing here raises into the reservation flow.
    """
    reservation = (
        Reservation.objects.select_related("facility", "requester", "created_by")
        .prefetch_related("items__equipment")
        .filter(pk=reservation_pk)
        .first()
    )
    if reservation is None:
        logger.warning(
            "Booking confirmation skipped: reservation %s no longer exists.",
            reservation_pk,
        )
        return False

    now = timezone.now()
    cutoff = now - CLAIM_TIMEOUT
    claimed = (
        Reservation.objects.filter(
            pk=reservation_pk,
            confirmation_email_sent_at__isnull=True,
        )
        .filter(
            Q(confirmation_email_claimed_at__isnull=True)
            | Q(confirmation_email_claimed_at__lt=cutoff)
        )
        .update(confirmation_email_claimed_at=now)
    )
    if not claimed:
        logger.info(
            "Booking confirmation skipped for reservation %s: already sent "
            "or a send is already in progress.",
            reservation.reservation_id,
        )
        return False

    try:
        ok, reason = send_booking_confirmation(reservation)
    except Exception:  # noqa: BLE001 — one email must never break creation
        ok, reason = False, "unexpected_error"
        logger.exception(
            "Unexpected error while sending the booking confirmation for "
            "reservation %s.",
            reservation.reservation_id,
        )

    if not ok:
        # Release the lease so a later attempt may retry, and log only a safe
        # category — never SMTP credentials or raw server responses.
        Reservation.objects.filter(
            pk=reservation_pk, confirmation_email_claimed_at=now
        ).update(confirmation_email_claimed_at=None)
        if reason == "no_email":
            logger.warning(
                "Booking confirmation skipped for reservation %s: the "
                "requester has no valid email address.",
                reservation.reservation_id,
            )
        else:
            logger.error(
                "Booking confirmation email FAILED for reservation %s "
                "(reason: %s). The reservation remains saved and unchanged.",
                reservation.reservation_id,
                reason,
            )
        return False

    Reservation.objects.filter(pk=reservation_pk).update(
        confirmation_email_sent_at=timezone.now(),
        confirmation_email_claimed_at=None,
    )
    logger.info(
        "Booking confirmation email sent for reservation %s (status: %s).",
        reservation.reservation_id,
        reservation.status,
    )
    return True
