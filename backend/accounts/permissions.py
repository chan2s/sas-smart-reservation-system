from rest_framework.permissions import SAFE_METHODS, BasePermission

#: The one 403 body every endpoint returns when an authenticated but
#: not-approved account attempts a state-changing request. The machine-readable
#: ``code`` lets the SPA key its view-only notice without parsing prose.
ACCOUNT_NOT_APPROVED_MESSAGE = {
    "detail": (
        "Your account is pending administrator approval. You currently have "
        "view-only access to SAS RESERVE."
    ),
    "code": "account_not_approved",
}


class IsAdmin(BasePermission):
    """Administrator only."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_admin
        )


class IsSasStaff(BasePermission):
    """Administrator or SAS staff."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_sas_staff
        )


class IsSasStaffOrReadOnly(BasePermission):
    """Everyone may read; only administrator/staff may write."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_sas_staff
        )


class IsAccountApproved(BasePermission):
    """Require an administrator-approved account for every request.

    The authoritative approval condition is the existing account-status flag
    (``User.is_approved``, backed by Django's built-in ``is_active``) — never a
    frontend flag or a value supplied in the request body. Used on endpoints
    that are entirely state-changing.
    """

    message = ACCOUNT_NOT_APPROVED_MESSAGE

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_approved)


class IsAccountApprovedOrReadOnly(BasePermission):
    """Authenticated accounts may read; only approved accounts may write.

    This is the global view-only policy, applied to every endpoint that can
    change system state. A not-approved account — including one that still
    holds a valid JWT issued before approval was revoked — may issue
    ``GET``/``HEAD``/``OPTIONS`` requests but receives ``403`` with a
    consistent body for ``POST``, ``PUT``, ``PATCH``, and ``DELETE``.

    Reads are deliberately allowed so a not-approved account can still view the
    dashboard, permitted facilities/equipment, reservation information and
    calendars, and its own profile/status.
    """

    message = ACCOUNT_NOT_APPROVED_MESSAGE

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return user.is_approved
