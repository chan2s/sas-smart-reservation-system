from django.urls import path
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsSasStaff

from . import oauth_views
from .models import AuditLog
from .views import (
    LoginView,
    MeView,
    RefreshView,
    RegisterView,
    TwoFactorBackupCodesView,
    TwoFactorDisableView,
    TwoFactorSetupView,
    TwoFactorStatusView,
    TwoFactorVerifyLoginView,
    TwoFactorVerifyView,
)

app_name = "accounts"


class AuditLogView(APIView):
    """GET /api/auth/audit-log/ — staff-only audit trail with filters.

    Supports ?action=, ?actor= (user id), ?search= (object repr / detail),
    ?page=. Read-only — audit entries are never editable through the API.
    """

    permission_classes = [permissions.IsAuthenticated, IsSasStaff]

    def get(self, request):
        from django.core.paginator import Paginator

        qs = AuditLog.objects.all().select_related("actor")

        action = request.query_params.get("action")
        if action:
            qs = qs.filter(action=action)
        actor = request.query_params.get("actor")
        if actor:
            qs = qs.filter(actor_id=actor)
        search = (request.query_params.get("search") or "").strip()
        if search:
            from django.db.models import Q

            qs = qs.filter(
                Q(object_repr__icontains=search)
                | Q(detail__icontains=search)
                | Q(actor_name__icontains=search)
            )

        paginator = Paginator(qs, 50)
        try:
            page = paginator.page(request.query_params.get("page", 1))
        except Exception:  # noqa: BLE001 — out-of-range/invalid page → last page
            page = paginator.page(paginator.num_pages)

        return Response(
            {
                "count": paginator.count,
                "num_pages": paginator.num_pages,
                "results": [
                    {
                        "id": entry.id,
                        "actor_name": entry.actor_name,
                        "action": entry.action,
                        "action_label": entry.get_action_display(),
                        "object_type": entry.object_type,
                        "object_id": entry.object_id,
                        "object_repr": entry.object_repr,
                        "detail": entry.detail,
                        "ip_address": entry.ip_address,
                        "created_at": entry.created_at,
                    }
                    for entry in page.object_list
                ],
            }
        )


urlpatterns = [
    path("login/", LoginView.as_view(), name="auth-login"),
    path("refresh/", RefreshView.as_view(), name="auth-refresh"),
    path("register/", RegisterView.as_view(), name="auth-register"),
    path("me/", MeView.as_view(), name="auth-me"),

    # Google OAuth (allauth-backed adapters + first-party JWT handoff).
    path("google/", oauth_views.google_config, name="google-config"),
    path("google/start/", oauth_views.google_start, name="google-start"),
    path("google/callback/", oauth_views.google_callback, name="google-callback"),

    # First-time Google sign-in email OTP verification.
    path("google/verify-otp/", oauth_views.google_verify_otp, name="google-verify-otp"),
    path("google/resend-otp/", oauth_views.google_resend_otp, name="google-resend-otp"),

    # Two-factor authentication (TOTP).
    path("2fa/status/", TwoFactorStatusView.as_view(), name="twofa-status"),
    path("2fa/setup/", TwoFactorSetupView.as_view(), name="twofa-setup"),
    path("2fa/verify/", TwoFactorVerifyView.as_view(), name="twofa-verify"),
    path("2fa/disable/", TwoFactorDisableView.as_view(), name="twofa-disable"),
    path("2fa/verify-login/", TwoFactorVerifyLoginView.as_view(), name="twofa-verify-login"),
    path("2fa/backup-codes/", TwoFactorBackupCodesView.as_view(), name="twofa-backup-codes"),
    path("audit-log/", AuditLogView.as_view(), name="audit-log"),
]
