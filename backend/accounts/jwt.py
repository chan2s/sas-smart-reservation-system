"""Custom JWT authentication.

django-otp's ``OTPMiddleware`` decorates ``request.user`` with an
``is_verified()`` method that requires a ``persistent_id`` attribute our
stateless JWT requests can't provide. DRF also evaluates permission classes
against the anonymous user during 401 handling. This subclass keeps JWT
verification identical to simplejwt's while making the user resolution
tolerant of both situations.

Security: tokens for accounts with pending first-time verification
(first_login_verified=False) are refused — a pending account can never
reach an authenticated API, even with a token minted before it became
pending or leaked from another route. The backend is authoritative; the
frontend is never trusted for this decision.
"""

from rest_framework_simplejwt.authentication import JWTAuthentication


def refresh_user_is_pending(refresh_token: str) -> bool:
    """True when a refresh token belongs to a pending (unverified) account.

    Used by the refresh endpoint to refuse re-minting access tokens for
    accounts whose first-time verification is (still or again) incomplete.
    Invalid tokens are not this function's concern — the parent view has
    already validated them by the time this is called.
    """
    if not refresh_token:
        return False
    try:
        from rest_framework_simplejwt.tokens import RefreshToken

        token = RefreshToken(refresh_token)
        user_id = token.payload.get("user_id")
        if user_id is None:
            return False
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.filter(pk=user_id).first()
        return bool(user and user.is_pending_verification)
    except Exception:  # noqa: BLE001 — malformed/expired → let the view 401
        return False


class SasJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        try:
            user = super().get_user(validated_token)
        except Exception:  # noqa: BLE001 — token invalid/expired/user gone → 401
            from rest_framework_simplejwt.exceptions import AuthenticationFailed

            raise AuthenticationFailed()

        if getattr(user, "is_pending_verification", False):
            from rest_framework_simplejwt.exceptions import AuthenticationFailed

            raise AuthenticationFailed(
                "Account is pending email verification.",
                code="pending_verification",
            )
        return user
