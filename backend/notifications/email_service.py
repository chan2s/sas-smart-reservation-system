"""
Email notification service for SAS RESERVE.

Handles sending email notifications for reservation status changes.
Uses Django's email infrastructure with environment-based SMTP configuration.
"""

import logging
from typing import Optional

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def send_reservation_email(
    recipient_email: str,
    subject: str,
    template_name: str,
    context: dict,
    fail_silently: bool = True,
) -> bool:
    """
    Send an email using a template.

    Args:
        recipient_email: The email address to send to.
        subject: Email subject line.
        template_name: Django template name (without .html).
        context: Template context variables.
        fail_silently: If True, log failures instead of raising.

    Returns:
        True if email was sent successfully, False otherwise.
    """
    try:
        message = render_to_string(f"emails/{template_name}.html", context)
        plain_message = render_to_string(f"emails/{template_name}.txt", context)

        sent = send_mail(
            subject=subject,
            message=plain_message,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "SAS RESERVE <noreply@example.com>"),
            recipient_list=[recipient_email],
            html_message=message,
            fail_silently=fail_silently,
        )
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
        "site_name": "SAS RESERVE",
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


def send_reservation_approved(
    user_email: str,
    reservation_id: str,
    event_name: str,
    facility_name: str,
    date: str,
    start_time: str,
    end_time: str,
) -> bool:
    """Send approval notification email."""
    return send_reservation_notification(
        user_email=user_email,
        reservation_id=reservation_id,
        event_name=event_name,
        facility_name=facility_name,
        date=date,
        start_time=start_time,
        end_time=end_time,
        status="APPROVED",
        status_label="Approved",
        message="Your reservation has been approved.",
        next_action="You can now check in at the facility on the event date.",
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
