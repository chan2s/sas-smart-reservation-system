from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from . import twofa
from .models import AuditLog
from .throttling import (
    AuthLoginThrottle,
    AuthRefreshThrottle,
    AuthRegisterThrottle,
    GlobalAnonThrottle,
    OtpVerifyThrottle,
)
from .serializers import (
    LoginSerializer,
    RegisterSerializer,
    UserSerializer,
)


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer
    throttle_classes = [GlobalAnonThrottle, AuthLoginThrottle]


class RefreshView(TokenRefreshView):
    """JWT refresh with a server-side account-status check.

    A refresh token from an earlier authentication state must not let a
    now-pending (first-time verification incomplete) account obtain a fresh
    access token. Normal refresh behavior for verified users is unchanged.
    """

    throttle_classes = [GlobalAnonThrottle, AuthRefreshThrottle]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        if response.status_code == 200:
            from .jwt import refresh_user_is_pending

            refresh_token = request.data.get("refresh") or ""
            if refresh_user_is_pending(refresh_token):
                return Response(
                    {"detail": "Account is pending email verification."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
        return response


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        serializer = self.get_serializer(
            self.get_object(), data=request.data, partial=partial
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [GlobalAnonThrottle, AuthRegisterThrottle]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        AuditLog.record(
            user,
            AuditLog.Action.REGISTER,
            object_type="auth",
            object_repr=user.display_name,
            request=request,
        )
        return Response(
            UserSerializer(user).data,
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Two-factor authentication (TOTP)
# ---------------------------------------------------------------------------


class TwoFactorStatusView(generics.RetrieveAPIView):
    """GET /api/auth/2fa/status/ — whether TOTP is enabled + codes remaining."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer  # unused; custom response

    def retrieve(self, request, *args, **kwargs):
        return Response(
            {
                "enabled": twofa.has_2fa(request.user),
                "backup_codes_remaining": twofa.remaining_backup_codes(request.user),
            }
        )


class TwoFactorSetupView(generics.GenericAPIView):
    """POST /api/auth/2fa/setup/ — create pending device, return QR + secret."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if twofa.has_2fa(request.user):
            return Response(
                {"detail": "Two-factor authentication is already enabled."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(twofa.start_setup(request.user))


class TwoFactorVerifyView(generics.GenericAPIView):
    """POST /api/auth/2fa/verify/ — activate pending device with a 6-digit code.

    Returns the one-time backup codes. The user must store them immediately;
    they are never retrievable again (only hashes are stored).
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        code = (request.data.get("code") or "").strip()
        backup_codes = twofa.confirm_setup(request.user, code)
        if not backup_codes:
            return Response(
                {
                    "detail": "That code didn't match. Check your authenticator "
                    "app and try again — codes rotate every 30 seconds."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        AuditLog.record(
            request.user,
            AuditLog.Action.SETTINGS_CHANGED,
            object_type="auth",
            object_repr="Two-factor authentication enabled",
            request=request,
        )
        return Response({"enabled": True, "backup_codes": backup_codes})


class TwoFactorDisableView(generics.GenericAPIView):
    """POST /api/auth/2fa/disable/ — requires current password (+ optional code)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        password = request.data.get("password") or ""
        totp_code = request.data.get("code") or ""
        if not twofa.disable(request.user, password, totp_code):
            return Response(
                {
                    "detail": "Two-factor authentication was not disabled. "
                    "Check your password (and code, if provided) and try again."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        AuditLog.record(
            request.user,
            AuditLog.Action.SETTINGS_CHANGED,
            object_type="auth",
            object_repr="Two-factor authentication disabled",
            request=request,
        )
        return Response({"enabled": False})


class TwoFactorVerifyLoginView(generics.GenericAPIView):
    """POST /api/auth/2fa/verify-login/ — complete a challenged login.

    Expects ``mfa_token`` from the login response plus a TOTP or backup code.
    Returns the JWT pair only when the code validates.
    """

    permission_classes = [permissions.AllowAny]
    throttle_classes = [GlobalAnonThrottle, OtpVerifyThrottle]

    def post(self, request):
        token = request.data.get("mfa_token") or ""
        code = request.data.get("code") or ""

        user = twofa.resolve_challenge(token)
        if user is None:
            return Response(
                {"detail": "This verification request has expired. Please sign in again."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if getattr(user, "is_pending_verification", False):
            # Pending first-time accounts cannot authenticate — even with a
            # valid 2FA challenge — until email verification completes.
            return Response(
                {"detail": "Account is pending email verification."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not twofa.verify_login(user, code):
            return Response(
                {
                    "detail": "Invalid or expired verification code. "
                    "Codes rotate every 30 seconds."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        from rest_framework_simplejwt.tokens import RefreshToken

        refresh = RefreshToken.for_user(user)
        AuditLog.record(
            user,
            AuditLog.Action.LOGIN_2FA,
            object_type="auth",
            object_repr="Signed in with two-factor authentication",
            request=request,
        )
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserSerializer(user).data,
            }
        )


class TwoFactorBackupCodesView(generics.GenericAPIView):
    """POST /api/auth/2fa/backup-codes/ — regenerate with a valid TOTP code."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        codes = twofa.regenerate_backup_codes(request.user, request.data.get("code") or "")
        if codes is None:
            return Response(
                {
                    "detail": "Could not regenerate backup codes. Enter a current "
                    "6-digit code from your authenticator app."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"backup_codes": codes})
