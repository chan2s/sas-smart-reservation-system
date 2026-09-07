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

from rest_framework.decorators import permission_classes, throttle_classes
from rest_framework_simplejwt.tokens import RefreshToken

from accounts import email_otp
from accounts.throttling import (
    GlobalAnonThrottle,
    GoogleStartThrottle,
    OtpResendThrottle,
    OtpVerifyThrottle,
)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

# Identity-only scopes — no Gmail, Drive, Contacts, or Calendar.
GOOGLE_SCOPES = ["openid", "email", "profile"]

STATE_MAX_AGE_SECONDS = 600


def _frontend_url(path: str) -> str:
    from django.conf import settings

    return f"{settings.PUBLIC_FRONTEND_URL.rstrip('/')}{path}"


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
            "redirect_uri": request.build_absolute_uri(
                reverse("accounts:google-callback")
            ),
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
                "and GOOGLE_CLIENT_SECRET to the backend environment."
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    redirect_uri = request.build_absolute_uri(reverse("accounts:google-callback"))
    nonce = secrets.token_urlsafe(16)
    state = TimestampSigner().sign_object({"n": nonce})

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
    frontend_error = lambda code: redirect(f"{_frontend_url('/login')}?google_error={code}")  # noqa: E731

    client_id, client_secret = _client_config()
    if not client_id or not client_secret:
        return frontend_error("not_configured")

    # 1. Validate OAuth state (CSRF protection).
    state = request.query_params.get("state") or ""
    try:
        TimestampSigner().unsign_object(state, max_age=STATE_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return frontend_error("invalid_state")

    # 2. Reject Google-reported errors (user cancelled consent, etc.).
    if request.query_params.get("error"):
        return frontend_error("cancelled")

    code = request.query_params.get("code")
    if not code:
        return frontend_error("missing_code")

    redirect_uri = request.build_absolute_uri(reverse("accounts:google-callback"))

    # 3. Exchange the authorization code — server-side only.
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
            return frontend_error("token_exchange_failed")
    except requests.RequestException:
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
    except requests.RequestException:
        return frontend_error("identity_failed")

    email = (userinfo.get("email") or "").lower()
    if not email or not userinfo.get("email_verified", False):
        return frontend_error("email_unverified")

    # 5. Resolve the local account — link, never duplicate.
    from django.contrib.auth import get_user_model
    from django_otp.plugins.otp_totp.models import TOTPDevice

    from accounts import email_otp

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
        # Server-authoritative pending state: a newly created Google account
        # is NOT verified until email OTP verification succeeds.
        user.first_login_verified = False
        user.save(update_fields=["role", "first_login_verified"])
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
        # (A pending first-time 2FA account stays blocked from Google login
        # until it completes email verification via the password flow.)
        return frontend_error("twofa_required")

    # SECURITY: "user exists" is NOT sufficient for authentication.
    # An account created by first-time Google sign-in remains PENDING
    # (first_login_verified=False) until the email OTP is verified. Google
    # verifying the email is not the same as SAS RESERVE verifying it.
    if not user.first_login_verified:
        # Pending account (newly created OR a re-entry after pressing Back
        # on the OTP page): locate/restart the verification session under
        # rate limits and redirect to the OTP page. NEVER issue a JWT.
        try:
            verification_token = email_otp.resume_pending(
                user, email, request=request
            )
        except email_otp.OtpError as exc:
            if exc.code == "email_failed":
                return frontend_error("otp_send_failed")
            if exc.code == "resend_cooldown":
                # Session is live and rate-limited; send them to the OTP
                # page without a token is useless — they need the token.
                # Reuse the still-valid session token if one exists, else
                # surface a friendly error for an immediate retry.
                return frontend_error("otp_cooldown")
            if exc.code == "resend_exhausted":
                return frontend_error("otp_resend_exhausted")
            return frontend_error("otp_send_failed")

        return redirect(
            f"{_frontend_url('/auth/verify-otp')}?token={quote(verification_token)}"
        )

    if created and user.first_login_verified:  # unreachable; defensive
        return frontend_error("otp_send_failed")

    AuditLog.record(
        user,
        AuditLog.Action.LOGIN,
        object_type="auth",
        object_repr="Google sign-in",
        request=request,
    )

    # 6b. Existing verified user: issue first-party JWTs — no Google tokens
    #     reach the browser.
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = RefreshToken.for_user(user)

    # 7. Hand off to the SPA with the JWT pair in the URL fragment
    #    (fragments are not sent to servers and not kept in history).
    fragment = f"access={quote(str(refresh.access_token))}&refresh={quote(str(refresh))}"
    return redirect(f"{_frontend_url('/auth/callback')}#{fragment}")


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([GlobalAnonThrottle, OtpVerifyThrottle])
def google_verify_otp(request):
    """POST /api/auth/google/verify-otp/ — complete first-time verification.

    Exchanges the pending session's ``verification_token`` + a 6-digit email
    OTP for the SAS RESERVE JWT pair. This is the ONLY path that authenticates
    a first-time Google account — the OAuth callback never issues tokens for
    new users, so OTP cannot be bypassed by crafting requests.
    """
    token = (request.data.get("verification_token") or "").strip()
    otp = (request.data.get("otp") or "").strip()

    try:
        user = email_otp.verify(token, otp, request=request)
    except email_otp.OtpError as exc:
        return Response(
            {"detail": exc.message, "code": exc.code},
            status=status.HTTP_400_BAD_REQUEST,
        )

    refresh = RefreshToken.for_user(user)
    AuditLog.record(
        user,
        AuditLog.Action.LOGIN,
        object_type="auth",
        object_repr="Google sign-in (email verified)",
        request=request,
    )
    return Response(
        {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": UserSerializer(user).data,
        }
    )


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([GlobalAnonThrottle, OtpResendThrottle])
def google_resend_otp(request):
    """POST /api/auth/google/resend-otp/ — send a fresh code (rate-limited)."""
    token = (request.data.get("verification_token") or "").strip()
    try:
        email_otp.resend(token, request=request)
    except email_otp.OtpError as exc:
        return Response(
            {"detail": exc.message, "code": exc.code},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return Response({"detail": "A new verification code has been sent."})
