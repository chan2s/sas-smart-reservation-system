"""TOTP two-factor authentication service.

Uses django-otp's TOTP devices plus hashed single-use backup codes.

Login flow (JWT-based SPA):
1. ``POST /api/auth/login/`` with valid credentials of a 2FA-enabled user
   returns ``{"mfa_required": true, "mfa_token": "<signed challenge>"}`` and
   **no** JWTs — the user is not authenticated yet.
2. ``POST /api/auth/2fa/verify/`` exchanges ``mfa_token`` + a 6-digit TOTP
   code (or a backup code) for the real JWT pair.

The challenge token is signed (Django signer) and short-lived; it only proves
"password step passed for this user" and grants nothing by itself.
"""

import base64
import io

import qrcode
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.utils import timezone
from django_otp.plugins.otp_totp.models import TOTPDevice

from .models import TwoFactorBackupCode

CHALLENGE_MAX_AGE_SECONDS = 300  # 5 minutes to complete the second step


# ---------------------------------------------------------------------------
# Signed challenge tokens
# ---------------------------------------------------------------------------


def issue_challenge(user) -> str:
    return TimestampSigner().sign_object({"uid": user.pk})


def resolve_challenge(token: str):
    """Return the user for a valid, unexpired challenge — else None."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    try:
        payload = TimestampSigner().unsign_object(
            token, max_age=CHALLENGE_MAX_AGE_SECONDS
        )
    except (BadSignature, SignatureExpired):
        return None
    return User.objects.filter(pk=payload.get("uid")).first()


def has_2fa(user) -> bool:
    if not getattr(user, "pk", None):
        return False
    return TOTPDevice.objects.filter(user=user, confirmed=True).exists()


# ---------------------------------------------------------------------------
# Device setup / teardown
# ---------------------------------------------------------------------------


def start_setup(user) -> dict:
    """Create an unconfirmed TOTP device and return QR + secret.

    The secret is transmitted once, over the authenticated API response, so
    the user can scan it. It is never logged.
    """
    TOTPDevice.objects.filter(user=user, confirmed=False).delete()
    # Issuer is injected into the otpauth:// URI from the OTP_TOTP_ISSUER
    # setting by django-otp — there is no per-device issuer field.
    device = TOTPDevice.objects.create(user=user, name="Authenticator", confirmed=False)
    config = device.config_url  # otpauth:// URI for authenticator apps

    encoded = (base64.b32encode(device.bin_key).decode("utf-8").rstrip("="),)  # type: ignore[union-attr]

    qr_image = qrcode.make(config)
    buffer = io.BytesIO()
    qr_image.save(buffer, format="PNG")
    qr_data_url = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()

    return {
        "secret": encoded[0],
        "otpauth_url": config,
        "qr_png_data_url": qr_data_url,
    }


def confirm_setup(user, code: str) -> bool:
    """Validate a 6-digit code against the pending device and activate 2FA."""
    device = TOTPDevice.objects.filter(user=user, confirmed=False).first()
    if device is None:
        return False
    normalized = (code or "").strip().replace(" ", "")
    if not normalized.isdigit() or not device.verify_token(normalized):
        return False
    device.confirmed = True
    device.save(update_fields=["confirmed"])
    # Fresh device → fresh backup codes.
    codes = TwoFactorBackupCode.generate(user)
    return codes  # noqa: RET504 — truthy list signals success


def disable(user, password: str, totp_code: str = "") -> bool:
    """Disable 2FA. Requires the account password; a valid TOTP or backup
    code may additionally be supplied (defense in depth)."""
    from django.contrib.auth import authenticate

    if not password:
        return False
    if not authenticate(username=user.username, password=password):
        return False
    if totp_code:
        normalized = totp_code.strip().replace(" ", "").replace("-", "").upper()
        device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
        totp_ok = bool(
            device
            and normalized.isdigit()
            and device.verify_token(normalized)
        )
        backup_ok = TwoFactorBackupCode.verify(user, normalized)
        if not (totp_ok or backup_ok):
            return False
    TOTPDevice.objects.filter(user=user).delete()
    TwoFactorBackupCode.objects.filter(user=user).delete()
    return True


def verify_login(user, code: str) -> bool:
    """Second login step: TOTP code or single-use backup code."""
    normalized = (code or "").strip().replace(" ", "").replace("-", "").upper()
    if not normalized:
        return False
    if normalized.isdigit():
        device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
        if device and device.verify_token(normalized):
            return True
    return TwoFactorBackupCode.verify(user, normalized)


def regenerate_backup_codes(user, totp_code: str) -> list[str] | None:
    """Issue a new backup-code batch; requires a valid current TOTP code."""
    device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
    normalized = (totp_code or "").strip().replace(" ", "")
    if not (device and normalized.isdigit() and device.verify_token(normalized)):
        return None
    return TwoFactorBackupCode.generate(user)


def remaining_backup_codes(user) -> int:
    return TwoFactorBackupCode.remaining(user)
