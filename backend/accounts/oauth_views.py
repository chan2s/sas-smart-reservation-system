"""Google OAuth endpoints for the React frontend.

Design notes:
* The OAuth state parameter is issued by this backend (signed via Django's
  signer + short-lived) so callbacks can be validated — allauth's session
  state store can't be used because the frontend is a separate origin and
  SPA requests don't share the session.
* The client secret stays on the server: React only ever talks to
  ``/api/auth/google/`` endpoints and is redirected to Google. The token
  exchange happens here. No secret, access token, or refresh token is ever
  returned to the browser — the SPA gets SAS RESERVE's own JWT pair.
* Scope is identity-only (openid email profile).
"""

import logging
import secrets
from urllib.parse import quote, urlencode

import requests
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.shortcuts import redirect
from django.urls import reverse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from accounts.models import AuditLog
from accounts.serializers import UserSerializer

from rest_framework.decorators import throttle_classes
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.throttling import GlobalAnonThrottle, GoogleStartThrottle

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

logger = logging.getLogger(__name__)

# Identity-only scopes — no Gmail, Drive, Contacts, or Calendar.
GOOGLE_SCOPES = ["openid", "email", "profile"]

STATE_MAX_AGE_SECONDS = 600


def _frontend_url(path: str, request=None, state_origin: str | None = None) -> str:
    """Frontend URL for redirecting the browser back to the SPA.

    Origin priority (see config/frontend.py): the origin embedded in the
    signed OAuth state (proven reachable — the browser used it to start the
    flow), then the request's own validated origin, then the configured
    production fallback. Never a hard-coded tunnel hostname.
    """
    from config.frontend import resolve_frontend_origin

    origin = resolve_frontend_origin(request, state_origin)
    return f"{origin}{path}"


def _oauth_redirect_uri(request, state_origin: str | None = None) -> str:
    """redirect_uri for Google — see config.frontend.oauth_redirect_uri."""
    from config.frontend import oauth_redirect_uri

    return oauth_redirect_uri(request, state_origin)


def _request_frontend_origin(request) -> str | None:
    """Validated browser-origin hint sent by the SPA (window.location.origin).

    The SPA includes its actual origin in the google-start request so the
    backend knows where the browser is even when the Vite proxy rewrites
    Host/Referer. Untrusted until it passes the same allowlist as every
    other origin — a hostile header changes nothing.
    """
    from config.frontend import frontend_origin_allowed

    candidate = (request.query_params.get("frontend_origin") or "").strip().rstrip("/")
    if candidate and frontend_origin_allowed(candidate):
        return candidate
    return None


def _client_config() -> tuple[str, str]:
    # Read lazily so environment/override changes are honored.
    from django.conf import settings

    return settings.GOOGLE_CLIENT_ID, settings.GOOGLE_CLIENT_SECRET


@api_view(["GET"])
@permission_classes([AllowAny])
def google_config(request):
    """Public client configuration (client id is public by design)."""
    client_id, _ = _client_config()
    if not client_id:
        return Response({"configured": False})
    return Response(
        {
            "configured": True,
            "client_id": client_id,
            "authorize_url": GOOGLE_AUTH_URL,
            "redirect_uri": _oauth_redirect_uri(request),
            "scope": GOOGLE_SCOPES,
        }
    )


@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([GlobalAnonThrottle, GoogleStartThrottle])
def google_start(request):
    """Redirect the browser to Google's consent screen.

    ``state`` is issued here (signed, short-lived, random nonce) and validated
    on callback — this is the CSRF protection for the OAuth flow.
    """
    client_id, _ = _client_config()
    if not client_id:
        return Response(
            {
                "detail": "Google sign-in is not configured. Add GOOGLE_CLIENT_ID "
                "and GOOGLE_CLIENT_SECRET to the backend server environment."
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    # Where is the browser? Prefer the SPA's own report of its origin
    # (window.location.origin) — survives the Vite dev proxy rewriting
    # Host/Referer — then fall back to request headers. Validated before
    # use; a spoofed value simply fails the allowlist and is dropped.
    from config.frontend import frontend_origin_allowed, request_origin

    browser_origin = _request_frontend_origin(request)
    if not browser_origin:
        header_origin = request_origin(request)
        if header_origin and frontend_origin_allowed(header_origin):
            browser_origin = header_origin
    state_origin = browser_origin or None

    redirect_uri = _oauth_redirect_uri(request, state_origin)
    nonce = secrets.token_urlsafe(16)

    # Bind the browser origin into the signed, short-lived state so the
    # callback returns the browser to the same environment (localhost /
    # 127.0.0.1 / current Dev Tunnel) it started from. Re-validated there.
    state = TimestampSigner().sign_object({"n": nonce, "o": state_origin})

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "state": state,
        "prompt": "select_account",
    }
    return Response({"authorize_url": f"{GOOGLE_AUTH_URL}?{urlencode(params)}"})


@api_view(["GET"])
@permission_classes([AllowAny])
def google_callback(request):
    """Validate state, exchange the code server-side, issue SAS JWTs.

    Errors redirect back to the React app with ``?google_error=…`` so the UI
    can show a friendly message; raw exceptions are never surfaced.
    """
    # The origin the browser used when the flow started — bound after the
    # signed state is validated below; error redirects before that fall back
    # to the request origin (see config/frontend.py).
    state_origin = None

    def frontend_error(code: str):
        return redirect(
            f"{_frontend_url('/login', request, state_origin)}?google_error={code}"
        )

    # 1. Validate OAuth state (CSRF protection) and recover the frontend
    #    origin the browser used when the flow started. May be None from
    #    older states; always re-validated before use, never trusted blind.
    state = request.query_params.get("state") or ""
    try:
        state_data = TimestampSigner().unsign_object(
            state, max_age=STATE_MAX_AGE_SECONDS
        )
    except (BadSignature, SignatureExpired):
        # Never log the raw state — it is signed but not secret-sensitive;
        # still, log only its length to keep Google payloads out of logs.
        logger.warning(
            "Google OAuth callback rejected: invalid/expired state "
            "(len=%s, ip=%s).",
            len(state),
            request.META.get("REMOTE_ADDR", ""),
        )
        return frontend_error("invalid_state")
    state_origin = (state_data or {}).get("o") or None

    client_id, client_secret = _client_config()
    if not client_id or not client_secret:
        logger.error(
            "Google OAuth callback aborted: GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET "
            "are not configured on the server."
        )
        return frontend_error("not_configured")

    # 2. Reject Google-reported errors (user cancelled consent, etc.).
    google_error = request.query_params.get("error")
    if google_error:
        logger.warning(
            "Google OAuth callback: Google returned error %r "
            "(ip=%s). Common causes: user cancelled consent, or "
            "redirect_uri/client mismatch at Google.",
            google_error,
            request.META.get("REMOTE_ADDR", ""),
        )
        return frontend_error("cancelled")

    code = request.query_params.get("code")
    if not code:
        logger.warning(
            "Google OAuth callback: no authorization code present (ip=%s).",
            request.META.get("REMOTE_ADDR", ""),
        )
        return frontend_error("missing_code")

    # Must be byte-identical to the redirect_uri used in google_start —
    # derived from the same validated origin, so it always is.
    redirect_uri = _oauth_redirect_uri(request, state_origin)

    # 3. Exchange the authorization code — server-side only. The request
    #    body (code/secret/tokens) is NEVER logged; only safe metadata is.
    try:
        token_response = requests.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        token_response.raise_for_status()
        access_token = token_response.json().get("access_token")
        if not access_token:
            logger.error(
                "Google token exchange returned no access_token "
                "(redirect_uri=%s, status=%s). If this persists, check that "
                "GOOGLE_REDIRECT_URI exactly matches an Authorized redirect "
                "URI in Google Cloud Console.",
                redirect_uri,
                token_response.status_code,
            )
            return frontend_error("token_exchange_failed")
    except requests.RequestException as exc:
        # Log only the exception class and the (non-secret) response status —
        # never the request body, tokens, or client secret.
        logger.error(
            "Google token exchange failed: %s (status=%s, redirect_uri=%s).",
            type(exc).__name__,
            getattr(getattr(exc, "response", None), "status_code", "n/a"),
            redirect_uri,
        )
        return frontend_error("token_exchange_failed")

    # 4. Fetch the verified identity.
    try:
        userinfo_response = requests.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        userinfo_response.raise_for_status()
        userinfo = userinfo_response.json()
    except requests.RequestException as exc:
        logger.error(
            "Google userinfo fetch failed: %s (status=%s).",
            type(exc).__name__,
            getattr(getattr(exc, "response", None), "status_code", "n/a"),
        )
        return frontend_error("identity_failed")

    email = (userinfo.get("email") or "").lower()
    if not email or not userinfo.get("email_verified", False):
        logger.warning(
            "Google OAuth: identity has no verified email (sub=%s).",
            userinfo.get("sub", "unknown"),
        )
        return frontend_error("email_unverified")

    # 5. Resolve the local account — link, never duplicate.
    from django.contrib.auth import get_user_model
    from django_otp.plugins.otp_totp.models import TOTPDevice

    User = get_user_model()
    user = User.objects.filter(email__iexact=email).first()
    created = False

    if user is None:
        # New user: plain REQUESTER, never privileged.
        username_base = email.split("@")[0].replace(".", "_")[:140] or "google_user"
        username = username_base
        suffix = 1
        while User.objects.filter(username=username).exists():
            suffix += 1
            username = f"{username_base}{suffix}"
        user = User.objects.create_user(
            username=username,
            email=email,
            first_name=userinfo.get("given_name", "")[:150],
            last_name=userinfo.get("family_name", "")[:150],
        )
        user.role = "REQUESTER"
        user.save(update_fields=["role"])
        created = True
        AuditLog.record(
            user,
            AuditLog.Action.GOOGLE_FIRST_ACCOUNT,
            object_type="auth",
            object_repr="Account created via first-time Google sign-in",
            request=request,
        )
    elif TOTPDevice.objects.filter(user=user, confirmed=True).exists():
        # Account has 2FA: do not let social sign-in bypass TOTP.
        logger.info(
            "Google OAuth: 2FA-gated account sign-in refused (user_id=%s).",
            user.pk,
        )
        return frontend_error("twofa_required")

    # 6. Audit and issue first-party JWTs — no Google tokens reach the
    #    browser. There is no email-verification gate: every Google account
    #    with a Google-verified email authenticates directly.
    AuditLog.record(
        user,
        AuditLog.Action.LOGIN,
        object_type="auth",
        object_repr="Google sign-in",
        request=request,
    )

    refresh = RefreshToken.for_user(user)

    # 7. Hand off to the SPA with the JWT pair in the URL fragment
    #    (fragments are not sent to servers and not kept in history).
    fragment = f"access={quote(str(refresh.access_token))}&refresh={quote(str(refresh))}"
    return redirect(
        f"{_frontend_url('/auth/callback', request, state_origin)}#{fragment}"
    )



