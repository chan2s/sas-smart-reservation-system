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
from typing import Optional

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.exceptions import TemplateDoesNotExist, TemplateSyntaxError
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

SAS_RESERVE_SITE_NAME = "SAS RESERVE"


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
    except Exception as e:
        if not fail_silently:
            raise
        logger.error(
            "Email delivery failed for %s: %s",
            recipient_email,
            str(e)[:200],  # Truncate to avoid logging sensitive data
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
        f"{item.quantity}× {item.equipment.name}" for item in reservation.items.all()
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

    The recipient is resolved from the reservation's own requester
    relationship (never from client-supplied data). Returns
    ``(success, error_category)`` where ``error_category`` is one of
    ``no_email``, ``smtp``, ``smtp_authentication``, ``invalid_recipient``,
    ``template``, ``connection``, or ``unknown`` (``None`` on success).
    """
    context = build_reservation_context(
        reservation,
        status=reservation.Status.APPROVED,
        status_label="Approved",
        message=(
            f"Your reservation {reservation.event_name} has been approved and is "
            f"confirmed for {reservation.date}."
        ),
        next_action="Check in at the facility at least 3 hours before your event start time.",
    )
    if actor and getattr(actor, "pk", None):
        context["approved_by"] = actor.display_name or "SAS Office"
    else:
        context["approved_by"] = "SAS Office"

    subject = "Your SAS RESERVE reservation has been approved"
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
            subject=subject,
            body=plain_message,
            from_email=getattr(
                settings, "DEFAULT_FROM_EMAIL", "SAS RESERVE <noreply@example.com>"
            ),
            to=[email],
        )
        message.attach_alternative(html_message, "text/html")
        sent = message.send(fail_silently=False)
        if sent:
            logger.info(
                "Approval email sent for reservation %s to %s (domain: %s)",
                reservation.reservation_id,
                email.split("@")[0] if "@" in email else "unknown",
                email.split("@")[1] if "@" in email else "unknown",
            )
            return True, None
        return False, "smtp"
    except Exception as exc:  # noqa: BLE001 — delivery must never break approval
        reason = _classify_email_error(exc)
        logger.error(
            "Approval email FAILED for reservation %s to %s: %s",
            reservation.reservation_id,
            email,
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