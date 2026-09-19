"""Environment-aware frontend-origin resolution (no hard-coded hostnames).

The OAuth hand-off must return the browser to the origin it actually came
from — ``localhost:5173``, a VS Code Dev Tunnel whose hostname changes on
every restart, or the production domain. Two sources of truth, in order:

1. **The signed OAuth state.** ``google_start`` embeds the browser origin
   (validated here) in the signed state it issues; ``google_callback`` reads
   it back after Google redirects. The round-trip through Google's redirect
   proves the browser can actually reach that origin, and the signature
   proves SAS RESERVE issued it — an attacker cannot stuff an arbitrary
   open-redirect origin into the flow.

2. **The request itself.** When no state origin exists (error redirects
   initiated by the backend), the request's ``Origin`` header or ``Host``
   is used — but *only* after passing the same validator. Production is
   pinned to ``PUBLIC_FRONTEND_URL`` so a stray Host header can never
   redirect tokens anywhere else.

Everything must pass :func:`frontend_origin_allowed` before it is trusted:

* explicit allowlist — ``FRONTEND_ALLOWED_ORIGINS`` env var
* Dev Tunnels — ``*.devtunnels.ms`` (HTTPS) when ``ALLOW_DEV_TUNNELS`` is on
* localhost / 127.0.0.1 — any port, but only when ``DEBUG`` is true

Nothing here logs origins together with tokens; the origin is not a secret,
but the resolver never touches token material at all.

The same helpers also derive the OAuth ``redirect_uri`` Google receives
(:func:`oauth_redirect_uri`): pinned to ``GOOGLE_REDIRECT_URI`` when set
(recommended — it must match a URI registered in Google Cloud Console
character-for-character), otherwise built from the *backend* host the
browser actually used. It is NEVER derived from the frontend origin — doing
so produces Google's ``redirect_uri_mismatch`` whenever only the backend
callback host is registered.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

from django.conf import settings

_DEV_TUNNEL_SUFFIX = ".devtunnels.ms"


def _allowed_origins() -> list[str]:
    """Explicit allowlist from the environment (exact scheme://host[:port])."""
    raw = os.environ.get("FRONTEND_ALLOWED_ORIGINS", "")
    return [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]


def _is_local(origin: str) -> bool:
    """localhost / 127.0.0.1 / [::1] on any port — dev convenience only."""
    if not settings.DEBUG:
        return False
    parsed = urlparse(origin)
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "::1")


def _is_dev_tunnel(origin: str) -> bool:
    """VS Code Dev Tunnels: https://<id>-<port>.<region>.devtunnels.ms.

    Hostname is validated (not just 'endswith') so ``evil-devtunnels.ms``
    cannot pass; HTTPS only, because tunnels are always TLS.
    """
    if not getattr(settings, "ALLOW_DEV_TUNNELS", False):
        return False
    parsed = urlparse(origin)
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").lower()
    return host.endswith(_DEV_TUNNEL_SUFFIX) and host != _DEV_TUNNEL_SUFFIX.lstrip(".")


def frontend_origin_allowed(origin: str) -> bool:
    """True only for origins this deployment explicitly trusts."""
    if not origin:
        return False
    origin = origin.rstrip("/")
    parsed = urlparse(origin)
    # A usable origin needs a scheme and a host; reject things like
    # "javascript:..." or bare hostnames early.
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    if origin in _allowed_origins():
        return True
    return _is_local(origin) or _is_dev_tunnel(origin)


def request_origin(request) -> str | None:
    """Best-effort origin of the browser's current location.

    Priority: ``Origin`` header (cross-origin navigations), ``Referer``
    origin (survives the Vite dev proxy, which rewrites Host to the backend
    but passes browser headers through), then the request's own scheme+host.
    Every result is untrusted until it passes
    :func:`frontend_origin_allowed`.
    """
    header = (request.headers.get("Origin") or "").strip()
    if header:
        return header.rstrip("/")
    referer = (request.headers.get("Referer") or "").strip()
    if referer:
        parsed = urlparse(referer)
        if parsed.scheme and parsed.hostname:
            # Rebuild scheme://host[:port] — drop path/query.
            netloc = parsed.netloc
            return f"{parsed.scheme}://{netloc}"
    scheme = "https" if request.is_secure() else "http"
    host = request.get_host()
    if not host:
        return None
    return f"{scheme}://{host}"


def resolve_frontend_origin(request, state_origin: str | None = None) -> str:
    """The origin to send the browser back to, in strict priority order.

    1. ``state_origin`` — what the browser used when the flow started
       (already validated when the state was issued; re-validated anyway).
    2. The request's own origin (Origin header / Host) — validated.
    3. ``settings.PUBLIC_FRONTEND_URL`` — the configured fallback, which in
       production is the pinned production domain.

    An empty string is never returned while PUBLIC_FRONTEND_URL is set, so
    callers can format f"{origin}/auth/callback" unconditionally.
    """
    if state_origin and frontend_origin_allowed(state_origin):
        return state_origin.rstrip("/")

    candidate = request_origin(request)
    if candidate and frontend_origin_allowed(candidate):
        return candidate

    return settings.PUBLIC_FRONTEND_URL.rstrip("/")


def _oauth_callback_path() -> str:
    """URL path of accounts:google-callback, resolved once at import time.

    The OAuth callback always lives on the Django backend — only the origin
    varies per environment, never the path.
    """
    from django.urls import reverse

    return reverse("accounts:google-callback")


_OAUTH_CALLBACK_PATH = _oauth_callback_path()


def oauth_redirect_uri(request, state_origin: str | None = None) -> str:
    """The ``redirect_uri`` to send to Google for the code exchange.

    The callback always lives on the Django backend, so the redirect_uri is
    built from where the browser actually reaches Django — never from the
    frontend origin. (Deriving it from the SPA origin caused Google's
    ``Error 400: redirect_uri_mismatch`` when only the backend callback
    host is registered in Google Cloud Console.)

    Priority:

    1. ``settings.GOOGLE_REDIRECT_URI`` — the explicit pin. It must match
       the Authorized redirect URI registered in Google Cloud Console
       character-for-character. Recommended whenever any proxy rewrites the
       Host header (e.g. the Vite dev proxy or Dev Tunnels), because the
       browser-visible host may differ from what Google has registered.
    2. ``request.build_absolute_uri`` — the host the browser actually used
       to reach Django (e.g. ``http://127.0.0.1:8000`` when Google redirects
       straight to the backend in local development).

    ``state_origin`` is accepted (and ignored) so callers can pass the
    signed-state origin uniformly; it only ever influences where the
    browser is sent *after* authentication, never the redirect_uri.
    """
    pinned = getattr(settings, "GOOGLE_REDIRECT_URI", "").strip()
    if pinned:
        return pinned

    # No pin: use the (ALLOWED_HOSTS-checked) request host. Google redirects
    # the browser to this same backend URL, so start and callback always
    # agree byte-for-byte.
    return request.build_absolute_uri(_OAUTH_CALLBACK_PATH)
