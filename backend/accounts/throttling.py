"""API rate limiting (DRF throttling).

Global defaults (all API endpoints inherit these via settings):
* ``anon``  — 60 requests/minute per IP
* ``user``  — 120 requests/minute per authenticated user

Stricter, endpoint-specific scopes protect abuse-prone operations:
* ``auth_login``      — 5/minute per IP (username/password)
* ``auth_register``   — 5/minute per IP
* ``auth_refresh``    — 30/minute per IP
* ``google_start``    — 10/minute per IP (OAuth entry)
* ``otp_verify``      — 5 per 10 minutes per IP
* ``otp_resend``      — 3 per 10 minutes per IP

Implementation notes:
* DRF's cache-based throttles use the configured Django cache. Set
  ``CACHES`` to a shared Redis backend in production so limits hold across
  workers/hosts; the locmem default is adequate for development.
* Keys are derived from ``get_ident()`` (request user id when
  authenticated, else REMOTE_ADDR). ``X-Forwarded-For`` is intentionally
  NOT trusted — Django fills REMOTE_ADDR from the real socket, and proxy
  deployments must configure their own middleware so spoofed headers
  cannot reset rate-limit buckets.
* Throttled responses are uniform JSON (429) and never expose internals.
"""

from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle, UserRateThrottle


def throttled_exception_handler(exc, context):
    """Return uniform JSON 429s with Retry-After; delegate the rest to DRF."""
    from rest_framework.exceptions import Throttled
    from rest_framework.response import Response
    from rest_framework.views import exception_handler as drf_exception_handler

    response = drf_exception_handler(exc, context)
    if isinstance(response, Response) and isinstance(exc, Throttled):
        retry_after = getattr(exc, "wait", None)
        if retry_after is not None:
            response["Retry-After"] = str(int(retry_after) + 1)
        response.data = {
            "detail": "Too many requests. Please try again later.",
        }
    return response


class GlobalAnonThrottle(AnonRateThrottle):
    scope = "anon"


class GlobalUserThrottle(UserRateThrottle):
    scope = "user"


class AuthLoginThrottle(AnonRateThrottle):
    """Username/password login — strict per-IP limit."""

    scope = "auth_login"


class AuthRegisterThrottle(AnonRateThrottle):
    scope = "auth_register"


class AuthRefreshThrottle(AnonRateThrottle):
    scope = "auth_refresh"


class GoogleStartThrottle(AnonRateThrottle):
    """OAuth consent entry — 10/minute per IP."""

    scope = "google_start"


class OtpVerifyThrottle(SimpleRateThrottle):
    """Email-OTP verification attempts — 5 per 10 minutes per IP."""

    scope = "otp_verify"
    rate = "5/600s"  # set directly; DRF only parses single-char periods
    duration = 600
    num_requests = 5

    def __init__(self):
        # Bypass parse_rate entirely — fixed duration/num_requests above.
        super().__init__()

    def get_rate(self):
        return self.rate

    def parse_rate(self, rate):
        return self.num_requests, self.duration

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


class OtpResendThrottle(SimpleRateThrottle):
    """OTP resend requests — 3 per 10 minutes per IP."""

    scope = "otp_resend"
    rate = "3/600s"
    duration = 600
    num_requests = 3

    def __init__(self):
        super().__init__()

    def get_rate(self):
        return self.rate

    def parse_rate(self, rate):
        return self.num_requests, self.duration

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }
