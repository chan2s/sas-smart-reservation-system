"""Custom JWT authentication.

Stateless JWT requests must fail cleanly as 401 when a token is invalid,
expired, or refers to an account that no longer exists — including while DRF
evaluates permission classes against the anonymous user during 401 handling.
This subclass keeps JWT verification identical to simplejwt's while making
user resolution tolerant of those situations.

It also enforces the active-account policy itself instead of inheriting it from
simplejwt's ``CHECK_USER_IS_ACTIVE`` setting: a deactivated account (an
administrator cleared ``is_active``) must not keep using an access token it was
issued before deactivation. Access tokens are stateless and cannot be revoked,
so the check happens on every request — the user row is the authority.
"""

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed


class SasJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        try:
            user = super().get_user(validated_token)
        except AuthenticationFailed:
            # Already a proper 401 (bad token, unknown user, inactive account).
            raise
        except Exception:  # noqa: BLE001 — token invalid/expired/user gone → 401
            raise AuthenticationFailed()

        if not user.is_active:
            raise AuthenticationFailed(
                "This account has been deactivated.", code="user_inactive"
            )

        return user
