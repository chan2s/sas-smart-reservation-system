"""
Email notification service for SAS RESERVE.

Handles sending email notifications for reservation status changes.
Uses Django's email infrastructure with environment-based SMTP configuration.

Sent emails never include:
* internal database ids (only the public ``reservation_id`` reference),
* private administrative notes or internal approval logs,
* credentials, tokens, or backend filesystem paths.
"""

import logging
import smtplib
import socket
import ssl
import time
from typing import Optional

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.exceptions import TemplateDoesNotExist, TemplateSyntaxError
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

SAS_RESERVE_SITE_NAME = "SAS RESERVE"

REMINDER_SUBJECT = "Reminder: Your SAS RESERVE Booking Is Coming Up"

BOOKING_CONFIRMATION_SUBJECT = "SAS RESERVE - Booking Confirmation"

CHECK_IN_INSTRUCTIONS = (
    "Please check in at the facility at least 3 hours before your event start "
    "time. Present your reservation reference number and a valid ID at the "
    "SAS Office or check-in desk."
)

#: Email subjects used across reservation notifications.
APPROVAL_SUBJECT = "Reservation Approved - SAS RESERVE"
REMINDER_SUBJECT = "Check-In Reminder - SAS RESERVE"
NO_SHOW_SUBJECT = "Reservation No-Show Notice - SAS RESERVE"
BOOKING_CONFIRMATION_SUBJECT = "SAS RESERVE - Booking Confirmation"

#: Subject of the signed approval-letter delivery email.
APPROVAL_LETTER_SUBJECT = "Approved Reservation Letter - {letter_id}"


def send_approval_letter_signed(letter, recipient_email: str) -> tuple[bool, Optional[str]]:
    """Email the SIGNED approval letter (PDF attached) to the requester.

    Reuses the project's reliable ``_deliver`` SMTP path and error
    classification. The PDF produced at signing time is attached; the DOCX is
    attached as well when one was generated. Returns
    ``(success, error_category)`` with the same categories as
    :func:`send_reservation_approved`; never raises into the caller, and never
    touches the letter itself (bookkeeping is the letters service's job).
    """
    from approval_letters.constants import SIGNATORY_NAME

    reference = letter.reservation.reservation_id
    subject = APPROVAL_LETTER_SUBJECT.format(letter_id=letter.letter_id)

    context = {
        "site_name": SAS_RESERVE_SITE_NAME,
        "requester_name": letter.requester_name
        or letter.reservation.requester_display_name,
        "letter_id": letter.letter_id,
        "reservation_id": reference,
        "event_name": letter.reservation.event_name,
        "facility_name": letter.reservation.facility.name,
        "date": letter.reservation.date,
        "start_time": letter.reservation.start_time,
        "end_time": letter.reservation.end_time,
        "signed_at": letter.signed_at,
        "signatory_name": SIGNATORY_NAME,
        "view_url": (
            f"{settings.PUBLIC_FRONTEND_URL.rstrip('/')}"
            f"/reservations/{letter.reservation.pk}"
        ),
        "has_docx": bool(letter.docx_file),
    }

    try:
        html_message = render_to_string("emails/approval_letter_signed.html", context)
        plain_message = render_to_string("emails/approval_letter_signed.txt", context)
    except Exception as exc:
        logger.error(
            "Signed-letter email template render failed for %s: %s",
            letter.letter_id,
            str(exc)[:200],
        )
        return False, _classify_email_error(exc)

    try:
        message = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=getattr(
                settings, "DEFAULT_FROM_EMAIL", "SAS RESERVE <noreply@example.com>"
            ),
            to=[recipient_email],
        )
        message.attach_alternative(html_message, "text/html")
        # Attach the finalized documents generated at signing time.
        with letter.pdf_file.open("rb") as pdf_handle:
            message.attach(
                letter.pdf_file.name.rsplit("/", 1)[-1], pdf_handle.read(), "application/pdf"
            )
        if letter.docx_file:
            with letter.docx_file.open("rb") as docx_handle:
                message.attach(
                    letter.docx_file.name.rsplit("/", 1)[-1],
                    docx_handle.read(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
        sent, send_exc = _deliver(message)
        if sent:
            logger.info(
                "Signed approval letter %s emailed for reservation %s (domain: %s).",
                letter.letter_id,
                reference,
                recipient_email.split("@")[1] if "@" in recipient_email else "unknown",
            )
            return True, None
        if send_exc is not None:
            reason = _classify_email_error(send_exc)
            logger.error(
                "Signed approval letter %s email FAILED for reservation %s "
                "(%s: %s) after %d connection attempts.",
                letter.letter_id,
                reference,
                type(send_exc).__name__,
                str(send_exc)[:200],
                SMTP_CONNECT_MAX_ATTEMPTS,
            )
            return False, reason
        return False, "smtp"
    except Exception as exc:  # noqa: BLE001 — delivery must never break signing
        reason = _classify_email_error(exc)
        logger.error(
            "Signed approval letter %s email FAILED for reservation %s (%s): %s",
            letter.letter_id,
            reference,
            type(exc).__name__,
            str(exc)[:200],
        )
        return False, reason


def send_reservation_email(
    recipient_email: str,
    subject: str,
    template_name: str,
    context: dict,
    fail_silently: bool = True,
) -> bool:
    """
    Send an email rendered from an HTML + plain-text template pair.

    Args:
        recipient_email: The email address to send to.
        subject: Email subject line.
        template_name: Django template name (without .html).
        context: Template context variables.
        fail_silently: If True, log failures instead of raising.

    Returns:
        True if email was handed to the email backend successfully.
    """
    try:
        html_message = render_to_string(f"emails/{template_name}.html", context)
        plain_message = render_to_string(f"emails/{template_name}.txt", context)

        message = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=getattr(
                settings, "DEFAULT_FROM_EMAIL", "SAS RESERVE <noreply@example.com>"
            ),
            to=[recipient_email],
        )
        message.attach_alternative(html_message, "text/html")
        sent = message.send(fail_silently=fail_silently)
        if sent:
            logger.info(
                "Email sent: %s to %s (domain: %s)",
                subject,
                recipient_email.split("@")[0] if "@" in recipient_email else "unknown",
                recipient_email.split("@")[1] if "@" in recipient_email else "unknown",
            )
            return True
        return False
    except Exception as exc:
        if not fail_silently:
            raise
        logger.error(
            "Email delivery failed for %s (%s): %s",
            recipient_email,
            type(exc).__name__,
            str(exc)[:200],  # Truncate to avoid logging sensitive data
        )
        return False


def _classify_email_error(exc: Exception) -> str:
    """Map an email exception to a short, safe category (never logs secrets)."""
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "smtp_authentication"
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "invalid_recipient"
    if isinstance(exc, (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected)):
        return "smtp_connection"
    if isinstance(exc, (TimeoutError, ConnectionError, smtplib.SMTPException)):
        return "smtp"
    if isinstance(exc, (TemplateDoesNotExist, TemplateSyntaxError)):
        return "template"
    if isinstance(exc, OSError):
        return "connection"
    return "unknown"


#: How long to wait between SMTP connection attempts. Gmail (and other relay
#: hosts) briefly drop connections when the same IP opens several sessions in
#: rapid succession; a short pause lets that throttle clear.
SMTP_CONNECT_RETRY_DELAY_SECONDS = 2
#: Upper bound for attempts. Total added latency in the total-failure case is
#: bounded by (attempts - 1) * delay, independent of EMAIL_TIMEOUT per try.
SMTP_CONNECT_MAX_ATTEMPTS = 3#: Exceptions that can only occur while the session is being established
#: (connect / DNS / TLS / login) - i.e. before ANY message bytes have
#: been transmitted. Retrying them is safe: a retry can never duplicate a
#: delivery. NOTE: this set must stay NARROW - including plain "OSError"
#: would also catch every ``smtplib.SMTPException`` (they subclass OSError),
#: silently retrying bad credentials and SMTP protocol errors on every
#: reconnect. ``SMTPAuthenticationError`` and ``SMTPRecipientsRefused`` are
#: deliberately NOT in this set: a reconnect cannot fix bad credentials, and
#: a refused recipient is permanent.
_TRANSIENT_CONNECTION_ERRORS = (
    ConnectionError,  # reset / aborted / refused / broken pipe
    TimeoutError,  # includes socket timeouts (connect and read)
    socket.gaierror,  # transient DNS resolution failure
    ssl.SSLError,  # transient TLS handshake drops
    smtplib.SMTPServerDisconnected,
    smtplib.SMTPConnectError,
)


def _deliver(message: "EmailMultiAlternatives") -> tuple[int, Optional[Exception]]:
    """Deliver ``message`` through Django's configured SMTP backend.

    The connection is opened explicitly (via the configured backend, so every
    setting - EMAIL_HOST, EMAIL_PORT, EMAIL_USE_TLS, credentials - still comes
    from the project's email configuration). A transient close during that
    establishment phase is retried up to :data:`SMTP_CONNECT_MAX_ATTEMPTS`
    times because nothing has been sent yet.    A disconnect DURING the message transmission (DATA) phase is never retried
    automatically: Gmail may already have accepted the message, so an
    immediate retry could deliver it twice. The ambiguous failure is returned
    to the caller for exact, type-level logging instead.

    Returns ``(accepted, exception)`` - ``accepted`` is the number of messages
    the backend accepted (0 or 1), and ``exception`` is ``None`` on success, an
    exception instance for a retried-out or transmit-phase failure, or ``None``
    together with ``accepted=0`` when the backend refused without raising.
    """
    last_open_exc: Optional[Exception] = None
    for attempt in range(1, SMTP_CONNECT_MAX_ATTEMPTS + 1):
        if attempt > 1:
            time.sleep(SMTP_CONNECT_RETRY_DELAY_SECONDS)
        connection = get_connection()
        try:
            connection.open()
        except _TRANSIENT_CONNECTION_ERRORS as exc:
            last_open_exc = exc
            logger.warning(
                "SMTP connection attempt %d/%d failed before any message was "
                "sent (%s: %s).",
                attempt,
                SMTP_CONNECT_MAX_ATTEMPTS,
                type(exc).__name__,
                str(exc)[:200],  # truncated; never includes credentials
            )
            continue
        # Routing the message through THIS opened connection reproduces
        # Django's normal ``message.send()`` path (EmailMessage.send() uses
        # ``self.connection``); it just skips throwing the freshly opened,
        # unusable connection away on a transient handshake drop.
        message.connection = connection
        try:
            accepted = int(message.send(fail_silently=False) or 0)
        finally:
            try:
                connection.close()
            except Exception:  # noqa: BLE001 — a failed close is harmless
                logger.debug("SMTP connection close failed (ignored).")
        logger.info(
            "Django email backend attempted delivery and accepted %d message(s).",
            accepted,
        )
        return (accepted, None)
    return (0, last_open_exc)


def build_reservation_context(
    reservation,
    status: str,
    status_label: str,
    message: str,
    next_action: Optional[str] = None,
) -> dict:
    """Shared context for reservation notification emails."""
    requester_name = reservation.requester_display_name
    if reservation.requester_type != reservation.RequesterType.EXTERNAL:
        requester_name = (
            reservation.requester.get_full_name()
            if reservation.requester and reservation.requester.get_full_name()
            else requester_name
        )
    resources = [
        f"{item.quantity}x {item.equipment.name}" for item in reservation.items.all()
    ]
    return {
        "site_name": SAS_RESERVE_SITE_NAME,
        "requester_name": requester_name,
        "reservation_id": reservation.reservation_id,
        "event_name": reservation.event_name,
        "facility_name": reservation.facility.name,
        "date": reservation.date,
        "start_time": reservation.start_time,
        "end_time": reservation.end_time,
        "resources": resources,
        "status": status,
        "status_label": status_label,
        "message": message,
        "next_action": next_action,
        "view_url": f"{settings.PUBLIC_FRONTEND_URL.rstrip('/')}/reservations/{reservation.id}",
    }


def send_reservation_approved(reservation, actor) -> tuple[bool, Optional[str]]:
    """Send the branded approval notification to the reservation requester.

    Uses the reliable ``_deliver`` path so a transient ``Connection unexpectedly
    closed`` / mid-handshake drop from Gmail is retried safely (before any message
    bytes are transmitted). Returns ``(success, error_category)`` where
    ``error_category`` is one of ``no_email``, ``smtp``, ``smtp_authentication``,
    ``invalid_recipient``, ``template``, ``connection``, or ``unknown``
    (``None`` on success).
    """
    context = build_reservation_context(
        reservation,
        status=reservation.Status.APPROVED,
        status_label="Approved",
        message=(
            f"Your reservation {reservation.event_name} has been approved and is "
            f"confirmed for {reservation.date}."
        ),
        next_action=CHECK_IN_INSTRUCTIONS,
    )
    if actor and getattr(actor, "pk", None):
        context["approved_by"] = actor.display_name or "SAS Office"
    else:
        context["approved_by"] = "SAS Office"

    try:
        html_message = render_to_string("emails/reservation_approved.html", context)
        plain_message = render_to_string("emails/reservation_approved.txt", context)
    except Exception as exc:
        logger.error(
            "Approval email template render failed for %s: %s",
            reservation.reservation_id,
            str(exc)[:200],
        )
        return False, _classify_email_error(exc)

    email = resolve_requester_email(reservation, actor)
    if not email:
        return False, "no_email"

    try:
        message = EmailMultiAlternatives(
            subject=APPROVAL_SUBJECT,
            body=plain_message,
            from_email=getattr(
                settings, "DEFAULT_FROM_EMAIL", "SAS RESERVE <noreply@example.com>"
            ),
            to=[email],
        )
        message.attach_alternative(html_message, "text/html")
        logger.info(
            "Approval email handed to the configured Django backend for "
            "reservation %s.",
            reservation.reservation_id,
        )
        sent, send_exc = _deliver(message)
        if sent:
            logger.info(
                "Approval email accepted (%d message) for reservation %s "
                "(recipient present, domain: %s).",
                sent,
                reservation.reservation_id,
                email.split("@")[1] if "@" in email else "unknown",
            )
            return True, None
        if send_exc is not None:
            reason = _classify_email_error(send_exc)
            logger.error(
                "Approval email FAILED for reservation %s (recipient present, "
                "domain: %s; %s: %s) after %d connection attempts.",
                reservation.reservation_id,
                email.split("@")[1] if "@" in email else "unknown",
                type(send_exc).__name__,
                str(send_exc)[:200],
                SMTP_CONNECT_MAX_ATTEMPTS,
            )
            return False, reason
        return False, "smtp"
    except Exception as exc:  # noqa: BLE001 — delivery must never break approval
        reason = _classify_email_error(exc)
        logger.error(
            "Approval email FAILED for reservation %s (recipient present, "
            "domain: %s; %s): %s",
            reservation.reservation_id,
            email.split("@")[1] if "@" in email else "unknown",
            type(exc).__name__,
            str(exc)[:200],
        )
        return False, reason


def send_reservation_checkin_reminder(
    reservation,
) -> tuple[bool, Optional[str]]:
    """Send the branded check-in reminder to the requester of an approved

    reservation. The message includes the scheduled start time and the existing
    check-in instructions (3-hour window; present the reservation reference and a
    valid ID at the SAS Office or check-in desk). It does not invent new
    check-in procedures.

    Returns ``(success, error_category)`` with the same categories as
    :func:`send_reservation_approved` (``no_email``, ``template``, ``smtp``,
    ``smtp_authentication``, ``invalid_recipient``, ``connection``,
    ``unknown``; ``None`` on success). Delivery never raises into the caller.
    """
    email = resolve_requester_email(reservation)
    if not email:
        return False, "no_email"

    context = build_reservation_context(
        reservation,
        status=reservation.Status.APPROVED,
        status_label="Approved",
        message=(
            f"This is a reminder that your reservation {reservation.event_name} "
            f"at {reservation.facility.name} is scheduled for "
            f"{reservation.date}. Please arrive on time for check-in."
        ),
        next_action=CHECK_IN_INSTRUCTIONS,
    )
    context["check_in_instructions"] = CHECK_IN_INSTRUCTIONS
    context["scheduled_check_in"] = (
        f"{reservation.start_datetime:%I:%M %p}".lstrip("0")
        if reservation.start_datetime is not None
        else None
    )

    try:
        html_message = render_to_string(
            "emails/reservation_checkin_reminder.html", context
        )
        plain_message = render_to_string(
            "emails/reservation_checkin_reminder.txt", context
        )
    except Exception as exc:  # noqa: BLE001 — report, never crash the sweep
        logger.error(
            "Check-in reminder email template render failed for %s: %s",
            reservation.reservation_id,
            str(exc)[:200],
        )
        return False, _classify_email_error(exc)

    try:
        message = EmailMultiAlternatives(
            subject=REMINDER_SUBJECT,
            body=plain_message,
            from_email=getattr(
                settings, "DEFAULT_FROM_EMAIL", "SAS RESERVE <noreply@example.com>"
            ),
            to=[email],
        )
        message.attach_alternative(html_message, "text/html")
        sent, send_exc = _deliver(message)
        if sent:
            logger.info(
                "Check-in reminder email sent for reservation %s to %s "
                "(domain: %s)",
                reservation.reservation_id,
                email.split("@")[0] if "@" in email else "unknown",
                email.split("@")[1] if "@" in email else "unknown",
            )
            return True, None
        if send_exc is not None:
            reason = _classify_email_error(send_exc)
            logger.error(
                "Check-in reminder email FAILED for reservation %s to %s "
                "(%s: %s) after %d connection attempts.",
                reservation.reservation_id,
                email,
                type(send_exc).__name__,
                str(send_exc)[:200],
                SMTP_CONNECT_MAX_ATTEMPTS,
            )
            return False, reason
        return False, "smtp"
    except Exception as exc:  # noqa: BLE001 — delivery must never break the sweep
        reason = _classify_email_error(exc)
        logger.error(
            "Check-in reminder email FAILED for reservation %s to %s (%s): %s",
            reservation.reservation_id,
            email,
            type(exc).__name__,
            str(exc)[:200],
        )
        return False, reason


def send_reservation_no_show_notice(
    reservation,
    actor,
) -> tuple[bool, Optional[str]]:
    """Send the branded no-show notice to the requester of a reservation that was

    marked as a no-show. The notice is intentionally plain and factual and does not
    invent penalties, fines, or restrictions that are not part of the existing
    application policy.

    Returns ``(success, error_category)`` with the same categories as
    :func:`send_reservation_approved` (``no_email``, ``template``, ``smtp``,
    ``smtp_authentication``, ``invalid_recipient``, ``connection``,
    ``unknown``; ``None`` on success). Delivery never raises into the caller.
    """
    email = resolve_requester_email(reservation, actor)
    if not email:
        return False, "no_email"

    context = build_reservation_context(
        reservation,
        status=reservation.Status.NO_SHOW,
        status_label="No-show",
        message=(
            f"Your reservation {reservation.reservation_id} for {reservation.event_name} "
            f"at {reservation.facility.name} on {reservation.date} "
            f"({reservation.start_time:%H:%M}-{reservation.end_time:%H:%M}) "
            "was marked as a no-show because check-in was not recorded within the "
            "allowed period."
        ),
        next_action=(
            "If you believe this was recorded in error, please contact the SAS Office "
            "as soon as possible."
        ),
    )
    context["marked_by"] = (
        actor.display_name if actor and getattr(actor, "pk", None) else "SAS Office"
    )

    try:
        html_message = render_to_string(
            "emails/reservation_no_show_notice.html", context
        )
        plain_message = render_to_string(
            "emails/reservation_no_show_notice.txt", context
        )
    except Exception as exc:  # noqa: BLE001 — report, never break the action
        logger.error(
            "No-show notice email template render failed for %s: %s",
            reservation.reservation_id,
            str(exc)[:200],
        )
        return False, _classify_email_error(exc)

    try:
        message = EmailMultiAlternatives(
            subject=NO_SHOW_SUBJECT,
            body=plain_message,
            from_email=getattr(
                settings, "DEFAULT_FROM_EMAIL", "SAS RESERVE <noreply@example.com>"
            ),
            to=[email],
        )
        message.attach_alternative(html_message, "text/html")
        sent, send_exc = _deliver(message)
        if sent:
            logger.info(
                "No-show notice email sent for reservation %s to %s "
                "(domain: %s)",
                reservation.reservation_id,
                email.split("@")[0] if "@" in email else "unknown",
                email.split("@")[1] if "@" in email else "unknown",
            )
            return True, None
        if send_exc is not None:
            reason = _classify_email_error(send_exc)
            logger.error(
                "No-show notice email FAILED for reservation %s to %s "
                "(%s: %s) after %d connection attempts.",
                reservation.reservation_id,
                email,
                type(send_exc).__name__,
                str(send_exc)[:200],
                SMTP_CONNECT_MAX_ATTEMPTS,
            )
            return False, reason
        return False, "smtp"
    except Exception as exc:  # noqa: BLE001 — delivery must never break the action
        reason = _classify_email_error(exc)
        logger.error(
            "No-show notice email FAILED for reservation %s to %s (%s): %s",
            reservation.reservation_id,
            email,
            type(exc).__name__,
            str(exc)[:200],
        )
        return False, reason


def send_booking_confirmation(reservation) -> tuple[bool, Optional[str]]:
    """Send the branded booking confirmation for a newly created reservation.

    The wording follows the reservation's SAVED status: a pending reservation
    is explicitly described as awaiting administrator approval, while an
    auto-approved one is described as confirmed. This function never changes
    the reservation and never raises into the caller - a failed delivery is
    reported so the caller can log it while the reservation remains intact.

    Returns ``(success, error_category)`` with the same categories as
    :func:`send_reservation_approved` (``no_email``, ``template``, ``smtp``,
    ``smtp_authentication``, ``invalid_recipient``, ``connection``,
    ``unknown``; ``None`` on success).
    """
    from django.utils import timezone

    from reservations.models import Reservation as ReservationModel

    email = resolve_requester_email(reservation)
    if not email:
        return False, "no_email"

    status = reservation.status
    status_label = reservation.get_status_display()
    if status == ReservationModel.Status.APPROVED:
        message = (
            "Your reservation request has been successfully recorded and "
            "approved. Your booking is confirmed."
        )
        next_action = CHECK_IN_INSTRUCTIONS
    elif status == ReservationModel.Status.PENDING:
        message = (
            "Your reservation request has been successfully recorded. It is "
            "currently awaiting administrator approval, so your booking is "
            "not yet confirmed."
        )
        next_action = (
            "No further action is needed right now. You can check your "
            "reservation status in SAS RESERVE at any time."
        )
    else:
        message = (
            "Your reservation request has been successfully recorded with the "
            f'status "{status_label}".'
        )
        next_action = (
            "You can check your reservation status in SAS RESERVE at any time."
        )

    context = build_reservation_context(
        reservation,
        status=status,
        status_label=status_label,
        message=message,
        next_action=next_action,
    )
    submitted_at = reservation.created_at or timezone.now()
    if timezone.is_aware(submitted_at):
        submitted_at = timezone.localtime(submitted_at)
    context["submitted_on"] = submitted_at
    context["is_approved"] = status == ReservationModel.Status.APPROVED
    context["is_pending"] = status == ReservationModel.Status.PENDING
    context["check_in_instructions"] = CHECK_IN_INSTRUCTIONS

    try:
        html_message = render_to_string(
            "emails/reservation_confirmation.html", context
        )
        plain_message = render_to_string(
            "emails/reservation_confirmation.txt", context
        )
    except Exception as exc:  # noqa: BLE001 — report, never break creation
        logger.error(
            "Booking confirmation template render failed for %s: %s",
            reservation.reservation_id,
            str(exc)[:200],
        )
        return False, _classify_email_error(exc)

    try:
        message = EmailMultiAlternatives(
            subject=BOOKING_CONFIRMATION_SUBJECT,
            body=plain_message,
            from_email=getattr(
                settings, "DEFAULT_FROM_EMAIL", "SAS RESERVE <noreply@example.com>"
            ),
            to=[email],
        )
        message.attach_alternative(html_message, "text/html")
        sent, send_exc = _deliver(message)
        if sent:
            logger.info(
                "Booking confirmation email sent for reservation %s to %s "
                "(status: %s, domain: %s)",
                reservation.reservation_id,
                email.split("@")[0] if "@" in email else "unknown",
                status,
                email.split("@")[1] if "@" in email else "unknown",
            )
            return True, None
        if send_exc is not None:
            reason = _classify_email_error(send_exc)
            logger.error(
                "Booking confirmation email FAILED for reservation %s to %s "
                "(%s: %s) after %d connection attempts.",
                reservation.reservation_id,
                email,
                type(send_exc).__name__,
                str(send_exc)[:200],
                SMTP_CONNECT_MAX_ATTEMPTS,
            )
            return False, reason
        return False, "smtp"

    except Exception as exc:  # noqa: BLE001 — delivery must never break creation
        reason = _classify_email_error(exc)
        logger.error(
            "Booking confirmation email FAILED for reservation %s to %s (%s): %s",
            reservation.reservation_id,
            email,
            type(exc).__name__,
            str(exc)[:200],
        )
        return False, reason


def send_reservation_reminder(reservation) -> tuple[bool, Optional[str]]:
    """Send the branded three-days-before reminder to the requester.

    Kept for backward compatibility with the in-app reminder Channel's existing
    email side-effect. New scheduled check-in reminders use
    :func:`send_reservation_checkin_reminder` so the reminder emails stay on the
    same reliable ``_deliver`` path.

    Returns ``(success, error_category)`` using the same categories as
    :func:`send_reservation_approved` (``no_email``, ``template``, ``smtp``,
    ``smtp_authentication``, ``invalid_recipient``, ``connection``,
    ``unknown``; ``None`` on success). Delivery never raises into the
    scheduler: a failure is reported so the caller can retry later.
    """
    email = resolve_requester_email(reservation)
    if not email:
        return False, "no_email"

    context = build_reservation_context(
        reservation,
        status=reservation.Status.APPROVED,
        status_label="Approved",
        message=(
            "Your reservation is scheduled within the next three days. "
            "Please review the details below and make the necessary "
            "preparations."
        ),
        next_action=CHECK_IN_INSTRUCTIONS,
    )
    context["check_in_instructions"] = CHECK_IN_INSTRUCTIONS

    try:
        html_message = render_to_string(
            "emails/reservation_reminder.html", context
        )
        plain_message = render_to_string(
            "emails/reservation_reminder.txt", context
        )
    except Exception as exc:  # noqa: BLE001 — report, never crash the sweep
        logger.error(
            "Reminder email template render failed for %s: %s",
            reservation.reservation_id,
            str(exc)[:200],
        )
        return False, _classify_email_error(exc)

    try:
        message = EmailMultiAlternatives(
            subject=REMINDER_SUBJECT,
            body=plain_message,
            from_email=getattr(
                settings, "DEFAULT_FROM_EMAIL", "SAS RESERVE <noreply@example.com>"
            ),
            to=[email],
        )
        message.attach_alternative(html_message, "text/html")
        sent, send_exc = _deliver(message)
        if sent:
            logger.info(
                "Reminder email sent for reservation %s to %s (domain: %s)",
                reservation.reservation_id,
                email.split("@")[0] if "@" in email else "unknown",
                email.split("@")[1] if "@" in email else "unknown",
            )
            return True, None
        if send_exc is not None:
            reason = _classify_email_error(send_exc)
            logger.error(
                "Reminder email FAILED for reservation %s to %s "
                "(%s: %s) after %d connection attempts.",
                reservation.reservation_id,
                email,
                type(send_exc).__name__,
                str(send_exc)[:200],
                SMTP_CONNECT_MAX_ATTEMPTS,
            )
            return False, reason
        return False, "smtp"
    except Exception as exc:  # noqa: BLE001 — delivery must never break the sweep
        reason = _classify_email_error(exc)
        logger.error(
            "Reminder email FAILED for reservation %s to %s (%s): %s",
            reservation.reservation_id,
            email,
            type(exc).__name__,
            str(exc)[:200],
        )
        return False, reason


def resolve_requester_email(reservation, actor=None) -> str:
    """Resolve the requester's email from the database relationship.

    Campus requesters use their account email. External requesters use the
    reservation's contact email. The acting/creating staff account is never
    used as a fallback recipient, and malformed addresses are rejected.
    """
    from django.core.exceptions import ValidationError
    from django.core.validators import validate_email

    if reservation.requester and reservation.requester.email:
        email = reservation.requester.email.strip()
    else:
        email = (reservation.contact_email or "").strip()
    if not email:
        return ""

    staff_emails = {
        u.email.strip()
        for u in (actor, reservation.created_by)
        if u is not None and getattr(u, "pk", None) and u.email
    }
    # Never let the *external* fallback collapse onto the approving/staff
    # account. When a real requester account exists the address above is the
    # authenticated relationship and is trusted by definition.
    if reservation.requester is None and email in staff_emails:
        return ""

    try:
        validate_email(email)
    except ValidationError:
        return ""
    return email


def send_reservation_notification(
    user_email: str,
    reservation_id: str,
    event_name: str,
    facility_name: str,
    date: str,
    start_time: str,
    end_time: str,
    status: str,
    status_label: str,
    message: str,
    next_action: Optional[str] = None,
) -> bool:
    """
    Send a reservation status notification email.

    Args:
        user_email: The requester's email address.
        reservation_id: The reservation ID (e.g., SAS-2024-00001).
        event_name: Name of the event.
        facility_name: Name of the facility.
        date: Event date (YYYY-MM-DD format).
        start_time: Start time (HH:MM format).
        end_time: End time (HH:MM format).
        status: Status code (PENDING, APPROVED, REJECTED, CANCELLED, etc.).
        status_label: Human-readable status label.
        message: Additional message/details about the status change.
        next_action: Optional next steps for the user.

    Returns:
        True if email was sent successfully.
    """
    subject = f"SAS RESERVE - Reservation {status_label}"

    context = {
        "reservation_id": reservation_id,
        "event_name": event_name,
        "facility_name": facility_name,
        "date": date,
        "start_time": start_time,
        "end_time": end_time,
        "status": status,
        "status_label": status_label,
        "message": message,
        "next_action": next_action,
        "site_name": SAS_RESERVE_SITE_NAME,
    }

    return send_reservation_email(
        recipient_email=user_email,
        subject=subject,
        template_name="reservation_notification",
        context=context,
    )


def send_reservation_submitted(
    user_email: str,
    reservation_id: str,
    event_name: str,
    facility_name: str,
    date: str,
    start_time: str,
    end_time: str,
) -> bool:
    """Send confirmation email when reservation is submitted."""
    return send_reservation_notification(
        user_email=user_email,
        reservation_id=reservation_id,
        event_name=event_name,
        facility_name=facility_name,
        date=date,
        start_time=start_time,
        end_time=end_time,
        status="PENDING",
        status_label="Submitted",
        message="Your reservation has been submitted and is awaiting approval.",
        next_action="Check your reservation status in the dashboard.",
    )


def send_reservation_rejected(
    user_email: str,
    reservation_id: str,
    event_name: str,
    facility_name: str,
    date: str,
    start_time: str,
    end_time: str,
    reason: str,
) -> bool:
    """Send rejection notification email."""
    return send_reservation_notification(
        user_email=user_email,
        reservation_id=reservation_id,
        event_name=event_name,
        facility_name=facility_name,
        date=date,
        start_time=start_time,
        end_time=end_time,
        status="REJECTED",
        status_label="Rejected",
        message=f"Your reservation was rejected. Reason: {reason}",
        next_action="Contact the SAS Office if you have questions.",
    )


def send_reservation_cancelled(
    user_email: str,
    reservation_id: str,
    event_name: str,
    facility_name: str,
    date: str,
    start_time: str,
    end_time: str,
    cancelled_by: str,
) -> bool:
    """Send cancellation notification email."""
    return send_reservation_notification(
        user_email=user_email,
        reservation_id=reservation_id,
        event_name=event_name,
        facility_name=facility_name,
        date=date,
        start_time=start_time,
        end_time=end_time,
        status="CANCELLED",
        status_label="Cancelled",
        message=f"Your reservation was cancelled by {cancelled_by}.",
        next_action="Contact the SAS Office if you need to reschedule.",
    )
