"""Custom JWT authentication.

django-otp's ``OTPMiddleware`` decorates ``request.user`` with an
``is_verified()`` method that requires a ``persistent_id`` attribute our
stateless JWT requests can't provide. DRF also evaluates permission classes
against the anonymous user during 401 handling. This subclass keeps JWT
verification identical to simplejwt's while making the user resolution
tolerant of both situations.
"""

from rest_framework_simplejwt.authentication import JWTAuthentication


class SasJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        try:
            user = super().get_user(validated_token)
        except Exception:  # noqa: BLE001 — token invalid/expired/user gone → 401
            from rest_framework_simplejwt.exceptions import AuthenticationFailed

            raise AuthenticationFailed()

        return user
