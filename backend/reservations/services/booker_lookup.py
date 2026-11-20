"""Returning-booker lookup with an email OTP gate.

The phone number is only a lookup hint. Saved details are never returned until
the caller proves control of the email address stored on the previous
reservation. Tokens are random, stored only as SHA-256 hashes, single-use, and
short-lived, so a database leak cannot be replayed.
"""

import datetime

from django.db import transaction
from django.utils import timezone

from accounts.organization_registry import (
    normalize_phone_number,
    organization_for_phone,
)
from reservations.models import BookerLookupVerification
from reservations.services.edit_verification import (
    generate_otp,
    generate_session_token,
    hash_otp,
    hash_session_token,
    verify_otp,
)

LOOKUP_TTL_MINUTES = 10
BOOKER_TOKEN_TTL_MINUTES = 30
MAX_ATTEMPTS = 5
RESEND_COOLDOWN_SECONDS = 60


class BookerLookupError(Exception):
    """A safe, client-facing lookup error."""

    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _email_on_file(organization, reservation) -> str:
    candidates = (
        (reservation.contact_email or "").strip() if reservation else "",
        (organization.contact_email or "").strip() if organization else "",
    )
    for value in candidates:
        if value and "@" in value:
            return value
    return ""


def start_lookup(phone: str):
    """Create an OTP challenge for the saved booker matching ``phone``.

    Returns ``(verification, otp, email)``. Raises :class:`BookerLookupError`
    when no successful reservation can be matched, without revealing whether
    the phone exists (callers surface the generic message).
    """
    canonical = normalize_phone_number(phone)
    if not canonical:
        raise BookerLookupError("Enter a valid Philippine mobile number.")

    organization, reservation = organization_for_phone(canonical)
    if organization is None and reservation is None:
        raise BookerLookupError(
            "We couldn't find saved details for that number.", status_code=404
        )

    email = _email_on_file(organization, reservation)
    if not email:
        raise BookerLookupError(
            "We couldn't find an email address on file for that number.",
            status_code=404,
        )

    now = timezone.now()
    otp = generate_otp()
    session_token = generate_session_token()
    with transaction.atomic():
        BookerLookupVerification.objects.filter(
            phone=canonical, consumed_at__isnull=True
        ).update(consumed_at=now)
        verification = BookerLookupVerification.objects.create(
            phone=canonical,
            organization=organization,
            contact_person=(reservation.contact_person or "")[:120]
            if reservation
            else (organization.contact_person or "")[:120],
            contact_email=email,
            otp_hash=hash_otp(otp),
            session_token_hash=hash_session_token(session_token),
            expires_at=now + datetime.timedelta(minutes=LOOKUP_TTL_MINUTES),
            resend_available_at=now + datetime.timedelta(seconds=RESEND_COOLDOWN_SECONDS),
        )
    return verification, otp, email, session_token


def _locked_verification(session_token: str):
    token_hash = hash_session_token(session_token) if session_token else ""
    return (
        BookerLookupVerification.objects.select_for_update()
        .filter(session_token_hash=token_hash, consumed_at__isnull=True)
        .first()
    )


def resend_lookup_otp(session_token: str):
    """Issue a fresh OTP for an unexpired lookup session."""
    now = timezone.now()
    with transaction.atomic():
        verification = _locked_verification(session_token)
        if verification is None:
            raise BookerLookupError("This verification session is no longer valid.")
        if now >= verification.expires_at:
            verification.consumed_at = now
            verification.save(update_fields=["consumed_at", "updated_at"])
            raise BookerLookupError("This verification code has expired. Start again.")
        if now < verification.resend_available_at:
            raise BookerLookupError(
                "Please wait before requesting another code.", status_code=429
            )
        otp = generate_otp()
        verification.otp_hash = hash_otp(otp)
        verification.attempts = 0
        verification.expires_at = now + datetime.timedelta(minutes=LOOKUP_TTL_MINUTES)
        verification.resend_available_at = now + datetime.timedelta(
            seconds=RESEND_COOLDOWN_SECONDS
        )
        verification.save(
            update_fields=[
                "otp_hash",
                "attempts",
                "expires_at",
                "resend_available_at",
                "updated_at",
            ]
        )
    return verification, otp


def verify_lookup(session_token: str, otp: str):
    """Verify the OTP and issue a single-use booker token."""
    if len(otp or "") != 6 or not otp.isdigit():
        raise BookerLookupError("Enter the six-digit verification code.")
    now = timezone.now()
    with transaction.atomic():
        verification = _locked_verification(session_token)
        if verification is None:
            raise BookerLookupError("This verification session is no longer valid.")
        if now >= verification.expires_at:
            verification.consumed_at = now
            verification.save(update_fields=["consumed_at", "updated_at"])
            raise BookerLookupError("This verification code has expired. Start again.")
        if verification.attempts >= MAX_ATTEMPTS:
            raise BookerLookupError("Too many incorrect codes. Start again.")
        if not verify_otp(otp, verification.otp_hash):
            verification.attempts += 1
            verification.save(update_fields=["attempts", "updated_at"])
            remaining = max(0, MAX_ATTEMPTS - verification.attempts)
            raise BookerLookupError(
                f"Incorrect code. {remaining} attempts remaining."
            )

        booker_token = generate_session_token()
        verification.booker_token_hash = hash_session_token(booker_token)
        verification.verified_at = now
        verification.expires_at = now + datetime.timedelta(
            minutes=BOOKER_TOKEN_TTL_MINUTES
        )
        verification.save(
            update_fields=[
                "booker_token_hash",
                "verified_at",
                "expires_at",
                "updated_at",
            ]
        )
    return verification, booker_token


def details_for(verification) -> dict:
    """Saved details eligible for autofill after OTP verification.
    
    Includes organization summary and recent reservation history.
    """
    from django.db.models import Count, Q
    from reservations.models import Reservation
    
    organization = verification.organization
    result = {
        "organization_id": organization.id if organization else None,
        "organization_name": organization.organization_name if organization else "",
        "organization_type": organization.organization_type if organization else "",
        "contact_person": verification.contact_person,
        "contact_email": verification.contact_email,
        "contact_phone": verification.phone,
    }
    
    # Add reservation history and summary if organization exists
    if organization:
        # Get all reservations for this organization
        reservations = organization.organization_reservations.select_related(
            "facility"
        ).order_by("-created_at")
        
        # Calculate summary statistics
        all_reservations = reservations.count()
        pending_count = reservations.filter(status__in=[
            Reservation.Status.PENDING, 
            Reservation.Status.APPROVED
        ]).count()
        approved_count = reservations.filter(
            status=Reservation.Status.APPROVED
        ).count()
        completed_count = reservations.filter(
            status=Reservation.Status.COMPLETED
        ).count()
        rejected_count = reservations.filter(
            status__in=[
                Reservation.Status.REJECTED,
                Reservation.Status.CANCELLED,
                Reservation.Status.EXPIRED,
                Reservation.Status.NO_SHOW,
            ]
        ).count()
        
        result["reservation_summary"] = {
            "total": all_reservations,
            "pending": pending_count,
            "approved": approved_count,
            "completed": completed_count,
            "rejected": rejected_count,
        }
        
        # Define pending statuses once for consistency
        pending_statuses = [Reservation.Status.PENDING, Reservation.Status.APPROVED]
        
        # Get pending reservations first (ordered by newest first)
        pending = reservations.filter(
            status__in=pending_statuses
        ).order_by("-created_at").values(
            "id",
            "reservation_id",
            "event_name",
            "date",
            "created_at",
            "status",
            "facility__name",
        )
        result["pending_reservations"] = list(pending)
        
        # Get recent reservations (last 5), EXCLUDING pending reservations
        # This ensures recent history never includes pending/approved reservations
        recent = reservations.exclude(
            status__in=pending_statuses
        ).order_by("-created_at")[:5].values(
            "id",
            "reservation_id",
            "event_name",
            "purpose",
            "date",
            "created_at",
            "status",
            "facility__name",
        )
        result["recent_reservations"] = list(recent)
    else:
        result["reservation_summary"] = {
            "total": 0,
            "pending": 0,
            "approved": 0,
            "completed": 0,
            "rejected": 0,
        }
        result["recent_reservations"] = []
        result["pending_reservations"] = []
    
    return result


def consume_booker_token(token: str):
    """Return the verification behind ``token`` and mark it consumed.

    The token can be used exactly once, and only until its expiry. An invalid,
    reused, or expired token simply returns ``None``.
    """
    if not token:
        return None
    now = timezone.now()
    token_hash = hash_session_token(token)
    with transaction.atomic():
        verification = (
            BookerLookupVerification.objects.select_for_update()
            .filter(
                booker_token_hash=token_hash,
                consumed_at__isnull=True,
                verified_at__isnull=False,
            )
            .first()
        )
        if verification is None or now >= verification.expires_at:
            return None
        verification.consumed_at = now
        verification.save(update_fields=["consumed_at", "updated_at"])
        return verification


def apply_booker_updates(reservation, token: str):
    """Link and refresh records for a verified returning booker.

    Only called after the reservation has been saved successfully. When the
    submitted organization still matches the verified record, that record is
    reused and its representative/contact details refreshed; when the booker
    changed the organization, the submitted name is resolved as its own record
    and the previous organization is left untouched.
    """
    from accounts.organization_registry import (
        link_reservation_organization,
        normalize_organization_name,
    )

    verification = consume_booker_token(token)
    if verification is None:
        return None

    organization = verification.organization
    same_organization = bool(
        organization
        and normalize_organization_name(reservation.organization)
        == normalize_organization_name(organization.organization_name)
    )
    if same_organization:
        reservation.organization_ref = organization
    return link_reservation_organization(
        reservation,
        create=True,
        trusted_update=same_organization,
    )
