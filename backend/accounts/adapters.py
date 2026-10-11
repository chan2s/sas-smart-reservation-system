"""django-allauth adapters: role safety + identity-based account linking.

Security rules enforced here:
* Google login NEVER grants Admin or SAS Staff. New social accounts always
  land as plain REQUESTER users.
* A Google identity is associated with a SAS RESERVE account only by the
  first-party callback (accounts.oauth_views), which binds Google's stable
  ``sub`` claim via the SocialAccount table. Email addresses are NOT a
  credential: matching an existing account by email never silently links the
  two — the user is sent to the login page instead so no password-protected
  account can be taken over.
* Secrets are never logged here or anywhere in the OAuth flow.
"""

from allauth.account.adapter import DefaultAccountAdapter
from allauth.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.shortcuts import redirect


class AllauthAccountAdapter(DefaultAccountAdapter):
    """Account adapter (local flows)."""

    def is_open_for_signup(self, request, sociallogin=None):
        return True


class SasSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Google sign-in behavior for SAS RESERVE."""

    def is_open_for_signup(self, request, sociallogin):
        return True

    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)
        # Role safety: Google authentication must never grant privileges.
        user.role = "REQUESTER"
        user.is_staff = False
        user.is_superuser = False
        return user

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        # Belt and braces: even if populate_user were bypassed, a social
        # signup can never be persisted with a privileged role.
        user.role = "REQUESTER"
        user.is_staff = False
        user.is_superuser = False
        user.save(update_fields=["role", "is_staff", "is_superuser"])
        return user

    def pre_social_login(self, request, sociallogin):
        """Never auto-link a social identity to an existing local account.

        Email addresses are not a credential. A Google identity is associated
        with a SAS RESERVE account only by the first-party callback
        (accounts.oauth_views), which binds Google's stable ``sub`` claim and
        refuses to link email/password accounts. If allauth's own social-login
        entry point is ever used, matching an existing account sends the user
        to the login page instead of silently connecting the two.
        """
        if sociallogin.is_existing:
            return

        email = (sociallogin.account.extra_data.get("email") or "").lower()
        if not email:
            return

        from django.contrib.auth import get_user_model

        if get_user_model().objects.filter(email__iexact=email).exists():
            raise ImmediateHttpResponse(
                redirect("/login?google_error=email_registered")
            )
