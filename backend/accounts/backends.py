"""Authentication backend for the SAS RESERVE account-approval policy.

SAS RESERVE reuses Django's built-in ``is_active`` flag as the authoritative
*account-approval* condition: an administrator clearing it revokes approval.
A not-approved account is not removed from the system — it is restricted to
view-only access by ``accounts.permissions.IsAccountApprovedOrReadOnly``.

For that restriction to be meaningful the account must still be able to
*sign in*, so this backend keeps Django's ``ModelBackend`` credential
verification (password hash, timing, permissions, groups) and removes only the
``is_active`` gate that would otherwise refuse authentication outright. The
active/approval decision is thereby moved from authentication to authorization
— exactly where the view-only policy is enforced.
"""

from django.contrib.auth.backends import ModelBackend


class AllowInactiveModelBackend(ModelBackend):
    """``ModelBackend`` that authenticates inactive (not-approved) accounts.

    Everything else — ``check_password``, ``user_can_authenticate``'s other
    responsibilities, permission/group resolution — is inherited unchanged.
    """

    def user_can_authenticate(self, user) -> bool:
        # Inactive ≠ unauthenticatable here: approval is enforced by the
        # permission layer, not by refusing a correct password.
        return user is not None
