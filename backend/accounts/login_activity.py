"""Server-side recording of successful sign-in events.

The SPA authenticates with first-party JWTs, so ``django.contrib.auth.login``
is not called on the password or Google OAuth paths — SimpleJWT's serializer
authenticates the credentials directly. This module is therefore the single
place that writes a ``LoginActivity`` row:

* an explicit ``record_login`` call from the JWT-issuing views
  (``LoginSerializer`` for email/password, ``google_callback`` for OAuth), and
* a ``user_logged_in`` signal receiver for any session-based login Django
  performs itself (for example the Django admin), so nothing is missed.

Only *successful* sign-ins are recorded. A failed attempt never reaches these
call sites, so it can never be stored as a success. No credential material
(password, OTP code, access/refresh token) is ever part of the row.
"""

from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from .models import LoginActivity


def record_login(user, *, method, request=None) -> LoginActivity | None:
    """Persist one successful login; never raise into the caller's flow.

    Returns the created row, or ``None`` when recording failed — a sign-in must
    never be blocked by an audit-writing problem.
    """
    if not getattr(user, "pk", None):
        return None
    try:
        return LoginActivity.objects.create(
            user=user,
            user_name=(user.get_full_name() or user.username or "")[:120],
            email=(user.email or "")[:254],
            role=user.role or "",
            method=method,
            status=LoginActivity.Status.SUCCESS,
            ip_address=(
                request.META.get("REMOTE_ADDR")
                if request is not None and hasattr(request, "META")
                else None
            ),
        )
    except Exception:  # noqa: BLE001 — audit must never break authentication
        return None


def record_password_login(user, request=None) -> LoginActivity | None:
    """Email/password (or any non-OAuth) credential sign-in."""
    return record_login(user, method=LoginActivity.Method.PASSWORD, request=request)


def record_google_login(user, request=None) -> LoginActivity | None:
    """Google OAuth sign-in, recorded by the first-party callback."""
    return record_login(user, method=LoginActivity.Method.GOOGLE, request=request)


@receiver(user_logged_in)
def _record_session_login(sender, request, user, **kwargs):  # noqa: ANN001
    """Catch session-based logins (e.g. the Django admin) the JWT paths skip."""
    record_password_login(user, request)
