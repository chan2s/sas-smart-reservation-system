"""Administrator-only user management and login activity endpoints.

Both surfaces are restricted to ``IsAdmin`` (the ``role == "ADMIN"`` accounts).
Ordinary users — including SAS staff — receive 403 and can never read another
account's identity, login history, or status through the API. The React UI
hides these pages for non-administrators as well, but the backend is the
authority.

Account status changes (deactivate / reactivate) reuse Django's built-in
``is_active`` flag; there is no second status field to drift out of sync with
the one Django, simplejwt, and the permission classes already honour.
"""

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from rest_framework import generics, permissions, status
from rest_framework.response import Response

from .models import AuditLog, LoginActivity
from .permissions import IsAdmin
from .serializers import AdminUserSerializer, LoginActivitySerializer

# Read the swapped-in user model directly so the queries below stay readable.
User = get_user_model()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _active_superuser_count() -> int:
    return User.objects.filter(is_superuser=True, is_active=True).count()


def deletion_block_reason(target, caller) -> str:
    """Why ``target`` may not be deleted by ``caller``, or ``""`` when allowed.

    Guards (all enforced server-side, independent of the UI):

    * an administrator can never delete their own current account;
    * a protected system account (a superuser) is never removable here;
    * the last active superuser can never be deleted, even indirectly.
    """
    if caller is not None and caller.pk == target.pk:
        return "You cannot delete your own account."
    if target.is_superuser:
        if _active_superuser_count() <= 1:
            return "The last active superuser account cannot be deleted."
        return "Protected system accounts cannot be deleted."
    return ""


def _parse_is_active(raw):
    """``True`` / ``False`` for a valid status payload, ``None`` otherwise.

    Only an explicit boolean is accepted — a missing, empty, or arbitrary value
    must never be read as "deactivate". JSON booleans and the equivalent
    form-encoded strings are both honoured.
    """
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str) and raw.strip().lower() in ("true", "false"):
        return raw.strip().lower() == "true"
    return None


def status_block_reason(target, caller, *, activating: bool) -> str:
    """Why ``caller`` may not change ``target``'s active flag, or ``""``.

    Guards (all enforced server-side, independent of the UI):

    * an administrator can never deactivate their own logged-in account;
    * a protected system account (a superuser) is never deactivated here;
    * the last active superuser can never be deactivated.

    Reactivating is deliberately *not* restricted the same way: it restores an
    account that already exists, grants no new privilege (role, password, and
    social links are untouched), and is the only path back for an account that
    was deactivated by mistake — including a superuser.
    """
    if activating:
        return ""
    if caller is not None and caller.pk == target.pk:
        return "You cannot deactivate your own account."
    if target.is_superuser:
        if _active_superuser_count() <= 1:
            return "The last active superuser account cannot be deactivated."
        return "Protected system accounts cannot be deactivated."
    return ""


class _AdminOnlyMixin:
    """Authenticated *and* administrator."""

    permission_classes = [permissions.IsAuthenticated, IsAdmin]


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------


class AdminUserListView(_AdminOnlyMixin, generics.ListAPIView):
    """GET /api/auth/users/ — paginated registered-user list (administrators).

    Filters: ``?search=`` (username / name / email / organization),
    ``?role=`` (ADMIN | STAFF | REQUESTER), ``?is_active=`` (true/false).
    Pagination is DRF's default (``count`` / ``next`` / ``previous`` /
    ``results``).
    """

    serializer_class = AdminUserSerializer

    def get_queryset(self):
        qs = User.objects.select_related("organization_ref").order_by(
            "-date_joined", "-id"
        )
        search = (self.request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(
                Q(username__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(email__icontains=search)
                | Q(organization__icontains=search)
                | Q(organization_ref__organization_name__icontains=search)
            )
        role = (self.request.query_params.get("role") or "").strip()
        if role:
            qs = qs.filter(role=role)
        is_active = (self.request.query_params.get("is_active") or "").strip().lower()
        if is_active in ("true", "false"):
            qs = qs.filter(is_active=is_active == "true")
        return qs


class AdminUserDeleteView(_AdminOnlyMixin, generics.GenericAPIView):
    """DELETE /api/auth/users/<pk>/ — remove an eligible account.

    The account is deleted inside a transaction that first *anonymizes*
    historical reservations (their ``requester`` FK is set to NULL) so the
    reservation history, audit trail, and login activity all survive. Audit and
    login rows are denormalized/SET_NULL and need no explicit handling.
    """

    serializer_class = AdminUserSerializer

    def get_object(self):
        return User.objects.filter(pk=self.kwargs["pk"]).first()

    def delete(self, request, *args, **kwargs):
        target = self.get_object()
        if target is None:
            return Response(
                {"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND
            )

        reason = deletion_block_reason(target, request.user)
        if reason:
            return Response({"detail": reason}, status=status.HTTP_400_BAD_REQUEST)

        identity = target.display_name
        target_pk = target.pk
        email = target.email

        with transaction.atomic():
            # Preserve history: detach reservations from the account instead of
            # letting the FK cascade delete them. Every other User reference is
            # already SET_NULL (kept) or a non-historical CASCADE (e.g. the
            # account's own notifications / social link), which is safe.
            from reservations.models import Reservation

            Reservation.objects.filter(requester=target).update(requester=None)
            target.delete()

        AuditLog.record(
            request.user,
            AuditLog.Action.USER_DELETED,
            object_type="user",
            object_id=target_pk,
            object_repr=identity,
            detail=f"Deleted account {identity} ({email})",
            request=request,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminUserStatusView(_AdminOnlyMixin, generics.GenericAPIView):
    """POST /api/auth/users/<pk>/status/ — activate or deactivate an account.

    Body: ``{"is_active": true|false}``. Deactivation flips Django's built-in
    ``is_active`` flag and nothing else: the account, its role, organization
    membership, password, Google link, reservations, and historical records
    are all preserved, and an administrator can reactivate it later.

    An inactive account can no longer authenticate (email/password or Google)
    and any token it already holds is rejected by ``accounts.jwt`` — the flag
    is the single source of truth for access, not the UI.

    Responses: 200 with the updated row, 400 for an invalid payload or a
    refused status change, 401 anonymous, 403 not an administrator, 404 no
    such account.
    """

    serializer_class = AdminUserSerializer

    def get_object(self):
        return User.objects.filter(pk=self.kwargs["pk"]).first()

    def post(self, request, *args, **kwargs):
        target = self.get_object()
        if target is None:
            return Response(
                {"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND
            )

        is_active = _parse_is_active(request.data.get("is_active"))
        if is_active is None:
            return Response(
                {"detail": 'Provide "is_active" as true or false.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reason = status_block_reason(target, request.user, activating=is_active)
        if reason:
            return Response({"detail": reason}, status=status.HTTP_400_BAD_REQUEST)

        # Idempotent: setting the flag it already has is a successful no-op and
        # is not audited (nothing changed).
        if target.is_active != is_active:
            target.is_active = is_active
            target.save(update_fields=["is_active"])
            AuditLog.record(
                request.user,
                (
                    AuditLog.Action.USER_REACTIVATED
                    if is_active
                    else AuditLog.Action.USER_DEACTIVATED
                ),
                object_type="user",
                object_id=target.pk,
                object_repr=target.display_name,
                detail=(
                    f"{'Reactivated' if is_active else 'Deactivated'} account "
                    f"{target.display_name} ({target.email})"
                ),
                request=request,
            )

        return Response(
            {
                "detail": (
                    "Account activated." if is_active else "Account deactivated."
                ),
                "user": self.get_serializer(target).data,
            }
        )


# ---------------------------------------------------------------------------
# Login activity
# ---------------------------------------------------------------------------


class LoginActivityListView(_AdminOnlyMixin, generics.ListAPIView):
    """GET /api/auth/login-activity/ — recent successful sign-ins (admins).

    Newest first (model ``Meta.ordering``). Filters: ``?search=`` (name /
    email), ``?user=`` (id), ``?method=`` (PASSWORD | GOOGLE), ``?date_from=``
    and ``?date_to=`` (ISO dates, inclusive, interpreted in the project
    timezone), plus ``?page=``.
    """

    serializer_class = LoginActivitySerializer

    def get_queryset(self):
        qs = LoginActivity.objects.select_related("user").all()
        params = self.request.query_params

        user_id = (params.get("user") or "").strip()
        if user_id.isdigit():
            qs = qs.filter(user_id=int(user_id))

        method = (params.get("method") or "").strip()
        if method:
            qs = qs.filter(method=method)

        search = (params.get("search") or "").strip()
        if search:
            qs = qs.filter(
                Q(user_name__icontains=search) | Q(email__icontains=search)
            )

        date_from = (params.get("date_from") or "").strip()
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        date_to = (params.get("date_to") or "").strip()
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        return qs
