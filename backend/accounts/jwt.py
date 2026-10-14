"""Custom JWT authentication.

Stateless JWT requests must fail cleanly as 401 when a token is invalid,
expired, or refers to an account that no longer exists — including while DRF
evaluates permission classes against the anonymous user during 401 handling.
This subclass keeps JWT verification identical to simplejwt's while making
user resolution tolerant of those situations.

Account approval is deliberately NOT enforced here. A token issued before an
administrator revoked approval must still *authenticate* so the request can be
answered as a read-only ``GET`` or a ``403`` for a state-changing method — see
``accounts.permissions.IsAccountApprovedOrReadOnly``. Refusing authentication
would turn every request (including reads) into a 401 and make view-only access
impossible, so ``CHECK_USER_IS_ACTIVE`` is disabled in settings and the
approval decision lives in the permission layer.
"""

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed


def user_authentication_rule(user) -> bool:
    """simplejwt's post-authenticate rule for the view-only policy.

    The default rule refuses an inactive account, which would make view-only
    access impossible. Credentials are already verified at this point, so the
    only requirement here is that an account actually resolved — approval is
    enforced later, per request, by the permission layer.
    """
    return user is not None


class SasJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        try:
            user = super().get_user(validated_token)
        except AuthenticationFailed:
            # Already a proper 401 (bad token, unknown user).
            raise
        except Exception:  # noqa: BLE001 — token invalid/expired/user gone → 401
            raise AuthenticationFailed()

        return user
