"""First-time Google sign-in email OTP verification.

Flow (new Google accounts only — existing accounts are untouched):
1. The OAuth callback creates the REQUESTER account, then a pending
   ``EmailOTPVerification`` session, and emails a 6-digit OTP.
2. The SPA receives a short-lived random ``verification_token`` (NOT a JWT)
   and collects the code.
3. ``POST /api/auth/google/verify-otp/`` exchanges token + OTP for the real
   SAS RESERVE JWT pair — only then is the account authenticated.

Security properties:
* OTP is generated with ``secrets`` and stored hashed (password hashers).
* OTP expires (10 min), is single-use, invalidated by resends.
* Attempts capped at 5 per session; resends capped at 5 with a 60 s cooldown.
* The verification token is random, stored hashed, single-purpose, and
  short-lived — possessing it only lets you complete THIS verification.
* The OTP is never returned by an API, never logged, never in a URL.
"""

import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from .models import (
    EmailOTPVerification,
    MAX_OTP_ATTEMPTS,
    MAX_OTP_RESENDS,
    OTP_LIFETIME_SECONDS,
    OTP_RESEND_COOLDOWN_SECONDS,
)

VERIFICATION_TOKEN_MAX_AGE_SECONDS = 1800  # 30 min to finish the session


class OtpError(Exception):
    """User-facing OTP failure. ``code`` selects the frontend error state."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _mask_email(email: str) -> str:
    """PII-safe display form for audit entries: ju***@example.com."""
    local, _, domain = email.partition("@")
    if not domain:
        return "***"
    shown = local[:2] if len(local) > 2 else local[:1]
    return f"{shown}***@{domain}"


# ---------------------------------------------------------------------------
# Creation / resending
# ---------------------------------------------------------------------------


def start_verification(user, email: str, *, request=None) -> str:
    """Create a pending session for ``user`` and email a fresh OTP.

    Returns the plaintext verification token for the SPA. Any previous
    pending session for the user is replaced, so only one OTP is ever live.
    Raises ``OtpError("email_failed")`` if sending fails (session rolled
    back so no unusable state is left behind).
    """
    from django.db import transaction

    # Server-authoritative pending state: the account is NOT verified until
    # email_otp.verify() succeeds — the only code path that flips it.
    if user.first_login_verified:
        user.first_login_verified = False
        user.save(update_fields=["first_login_verified"])

    otp = f"{secrets.randbelow(1_000_000):06d}"
    token = secrets.token_urlsafe(32)
    now = timezone.now()

    try:
        with transaction.atomic():
            EmailOTPVerification.objects.filter(user=user).delete()
            EmailOTPVerification.objects.create(
                user=user,
                email=email,
                otp_hash=make_password(otp),
                token_hash=make_password(token),
                expires_at=now + timedelta(seconds=OTP_LIFETIME_SECONDS),
                last_sent_at=now,
            )
            _send_otp_email(email, otp, first_send=True)
    except Exception as exc:  # noqa: BLE001 — surface a friendly error only
        if isinstance(exc, OtpError):
            raise
        raise OtpError(
            "email_failed",
            "We couldn't send the verification code. Please try again.",
        ) from exc

    from .models import AuditLog

    AuditLog.record(
        user,
        AuditLog.Action.OTP_SENT,
        object_type="auth",
        object_repr=f"Email verification code sent to {_mask_email(email)}",
        detail="First-time Google sign-in verification",
        request=request,
    )
    return token


def resend(token: str, *, request=None) -> None:
    """Issue a new OTP for a pending session (rate-limited).

    The new OTP invalidates the previous one. Errors carry a machine-readable
    code so the SPA can render cooldown / exhausted / expired states.
    """
    session = _resolve_session(token)
    now = timezone.now()

    if session.verified_at:
        raise OtpError(
            "already_verified", "This email address has already been verified."
        )
    if session.is_exhausted:
        raise OtpError(
            "resend_exhausted",
            "Too many code requests. Please start a new sign-in.",
        )
    if session.last_sent_at and now - session.last_sent_at < timedelta(
        seconds=OTP_RESEND_COOLDOWN_SECONDS
    ):
        raise OtpError("resend_cooldown", "Please wait before requesting another code.")

    otp = f"{secrets.randbelow(1_000_000):06d}"
    try:
        session.otp_hash = make_password(otp)
        session.expires_at = now + timedelta(seconds=OTP_LIFETIME_SECONDS)
        session.attempts = 0
        session.resend_count += 1
        session.last_sent_at = now
        session.save(
            update_fields=[
                "otp_hash",
                "expires_at",
                "attempts",
                "resend_count",
                "last_sent_at",
            ]
        )
        _send_otp_email(session.email, otp, first_send=False)
    except Exception as exc:  # noqa: BLE001
        if isinstance(exc, OtpError):
            raise
        raise OtpError(
            "email_failed",
            "We couldn't send the verification code. Please try again.",
        ) from exc

    from .models import AuditLog

    AuditLog.record(
        session.user,
        AuditLog.Action.OTP_RESENT,
        object_type="auth",
        object_repr=f"Email verification code resent to {_mask_email(session.email)}",
        request=request,
    )


def resume_pending(user, email: str, *, request=None) -> str:
    """Re-enter a pending verification (e.g. user restarted Google sign-in).

    Locates the pending account's session and reuses it when still valid.
    If the session expired, a fresh one is issued (rate-limited by the
    cooldown). The user remains pending; no verification state changes.

    Returns the plaintext verification token for the SPA redirect.
    """
    session = EmailOTPVerification.objects.filter(user=user).order_by("-created_at").first()
    now = timezone.now()

    session_expired = session is None or session.is_expired

    if session_expired:
        # Expired (or missing) session → start a fresh one. This respects
        # the resend cooldown via the same rate limiting as resend().
        if (
            session is not None
            and session.last_sent_at
            and now - session.last_sent_at < timedelta(seconds=OTP_RESEND_COOLDOWN_SECONDS)
        ):
            raise OtpError("resend_cooldown", "Please wait before requesting another code.")
        return start_verification(user, email, request=request)

    # Still-valid session: reuse it and email a fresh OTP only when the
    # user asked again well after the last send (respect the cooldown).
    if session.last_sent_at and now - session.last_sent_at < timedelta(
        seconds=OTP_RESEND_COOLDOWN_SECONDS
    ):
        # Within cooldown: reuse the current token — no email, no reset.
        # Return the token only if we can recover it... we can't (hashed).
        # Instead tell the SPA to redirect with a fresh link tied to the
        # SAME session: issue a new token bound to the existing session.
        token = _reissue_session_token(session)
        return token

    # Cooldown elapsed → send a fresh OTP (invalidates the previous one),
    # respecting the resend budget.
    if session.is_exhausted:
        raise OtpError(
            "resend_exhausted",
            "Too many code requests. Please start a new sign-in.",
        )
    token = _reissue_session_token(session)
    resend(token, request=request)
    return token


def _reissue_session_token(session) -> str:
    """Bind a fresh random token to an existing session (old one dies)."""
    token = secrets.token_urlsafe(32)
    session.token_hash = make_password(token)
    session.save(update_fields=["token_hash"])
    return token


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def verify(token: str, otp: str, *, request=None):
    """Validate the OTP for a session; return the user on success.

    On success the session and OTP are consumed. Failure modes raise
    ``OtpError`` with codes ``invalid_token`` / ``expired`` / ``locked`` /
    ``invalid_otp`` — and every failed attempt is audited.
    """
    session = _resolve_session(token)

    if session.verified_at:
        raise OtpError(
            "already_verified", "This email address has already been verified."
        )
    if session.is_locked:
        raise OtpError(
            "too_many_attempts",
            "Too many verification attempts. Please request a new code.",
        )
    if session.is_expired:
        raise OtpError(
            "expired",
            "This verification code has expired. Please request a new code.",
        )

    normalized = (otp or "").strip().replace(" ", "")
    session.attempts += 1
    session.save(update_fields=["attempts"])

    if not normalized or not check_password(normalized, session.otp_hash):
        from .models import AuditLog

        AuditLog.record(
            session.user,
            AuditLog.Action.OTP_FAILED,
            object_type="auth",
            object_repr="Incorrect email verification code",
            detail=f"attempt {session.attempts}/{MAX_OTP_ATTEMPTS}",
            request=request,
        )
        if session.is_locked:
            raise OtpError(
                "too_many_attempts",
                "Too many verification attempts. Please request a new code.",
            )
        raise OtpError("invalid_otp", "Invalid verification code.")

    # Success — consume the session atomically (single-use guarantee) and
    # flip the persistent verification state. This is the ONLY code path
    # that marks a first-time Google account as verified.
    from django.db import transaction

    with transaction.atomic():
        updated = EmailOTPVerification.objects.filter(
            pk=session.pk, verified_at__isnull=True
        ).update(verified_at=timezone.now())
    if not updated:  # concurrent use raced us — treat as already consumed
        raise OtpError("already_verified", "This email address has already been verified.")

    if not session.user.first_login_verified:
        session.user.first_login_verified = True
        session.user.save(update_fields=["first_login_verified"])

    from .models import AuditLog

    AuditLog.record(
        session.user,
        AuditLog.Action.OTP_VERIFIED,
        object_type="auth",
        object_repr="Email address verified (first-time Google sign-in)",
        request=request,
    )
    return session.user


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _resolve_session(token: str) -> EmailOTPVerification:
    """Find a pending session by its hashed token.

    Candidate rows are selected by recency and matched against their hash;
    an unknown/expired-token failure is deliberately indistinguishable from
    a wrong-token failure and yields the same user-facing error.
    """
    if not token:
        raise OtpError("invalid_token", "This verification link is invalid or has expired.")

    from django.db.models import Q

    candidates = EmailOTPVerification.objects.filter(
        expires_at__gte=timezone.now() - timedelta(seconds=OTP_LIFETIME_SECONDS),
    ).order_by("-created_at")[:20]
    for session in candidates:
        if check_password(token, session.token_hash):
            return session
    raise OtpError("invalid_token", "This verification link is invalid or has expired.")


def _send_otp_email(email: str, otp: str, *, first_send: bool) -> None:
    """Deliver the OTP. Never logs or returns the code itself."""
    subject = (
        "SAS RESERVE — Verify your email to finish signing in"
        if first_send
        else "SAS RESERVE — Your new verification code"
    )
    context = {
        "otp": otp,
        "minutes": OTP_LIFETIME_SECONDS // 60,
        "first_send": first_send,
    }
    text_body = render_to_string("accounts/email/otp.txt", context)
    html_body = render_to_string("accounts/email/otp.html", context)

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email],
    )
    message.attach_alternative(html_body, "text/html")
    # send() may raise on SMTP failure; the caller converts that to a
    # friendly OtpError without leaking credentials or internals.
    message.send(fail_silently=False)
