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

#: The consistent refusal for the designated approval-letter signatory when it
#: attempts to use any module other than Approval Letters.
APPROVAL_LETTERS_ONLY_MESSAGE = {
    "detail": (
        "Your account is limited to the Approval Letters module. It cannot "
        "access reservations, facilities, equipment, users, or settings."
    ),
    "code": "approval_letters_only",
}

#: Paths the module-scoped signatory may still use. The profile is needed to
#: render the signed-in shell, notifications carry the "letter awaiting your
#: review" notice, and the approval-letter endpoints are the module itself.
APPROVAL_SIGNATORY_ALLOWED_PREFIXES = (
    "/api/approval-letters/",
    "/api/auth/me/",
)


def approval_signatory_path_allowed(path: str) -> bool:
    """Whether a module-scoped signatory may call ``path``."""
    return any((path or "").startswith(prefix) for prefix in APPROVAL_SIGNATORY_ALLOWED_PREFIXES)


def is_module_scoped_signatory(user) -> bool:
    """Safe accessor usable with AnonymousUser and lazy request users."""
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and getattr(user, "is_approval_letters_only", False)
    )


class IsAdmin(BasePermission):
    """Administrator only."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_admin
        )


class IsSasStaff(BasePermission):
    """Administrator or SAS staff.

    The module-scoped approval-letter signatory is intentionally excluded: its
    ``User.is_sas_staff`` property reports False so it can never reach the
    reservation, facility, equipment, analytics, or user-management surfaces.
    """

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_sas_staff
        )


class IsApprovalSignatory(BasePermission):
    """The designated approval-letter signatory (server-verified).

    Administrator status alone is not enough — the explicit designation is
    required, matching the existing signatory support. The account-approval
    policy is layered separately by ``IsAccountApprovedOrReadOnly``.
    """

    message = {
        "detail": "Only the designated approval-letter signatory may approve letters.",
        "code": "not_approval_signatory",
    }

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and getattr(user, "is_authorized_letter_approver", False)
        )


class IsApprovalLetterStaffOrSignatory(BasePermission):
    """SAS staff or the designated signatory — for approval-letter support actions."""

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (
                getattr(user, "is_sas_staff", False)
                or getattr(user, "is_authorized_letter_approver", False)
            )
        )


class IsApprovalModuleScopeAllowed(BasePermission):
    """Deny a module-scoped signatory on endpoints that only require authentication.

    Most views include ``IsAccountApprovedOrReadOnly``, which enforces the same
    scope. This class covers the remaining read/compute endpoints (calendar,
    availability, pricing, dashboard summary) that use plain ``IsAuthenticated``
    so the restriction is complete rather than merely hidden in the SPA.
    """

    message = APPROVAL_LETTERS_ONLY_MESSAGE

    def has_permission(self, request, view):
        return not is_module_scoped_signatory(request.user)


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
        # A designated signatory is a single-module account: outside Approval
        # Letters (plus its own profile and notification feed) it is refused
        # outright, including for otherwise-public reads. The check runs before
        # the view-only policy so the response names the real restriction.
        if is_module_scoped_signatory(user) and not approval_signatory_path_allowed(
            request.path
        ):
            self.message = APPROVAL_LETTERS_ONLY_MESSAGE
            return False
        if request.method in SAFE_METHODS:
            return True
        return user.is_approved
