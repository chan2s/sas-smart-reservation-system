"""django-allauth adapters: role safety + automatic account linking.

Security rules enforced here:
* Google login NEVER grants Admin or SAS Staff. New social accounts always
  land as plain REQUESTER users.
* Signing in with Google using the email of an existing account links the
  identity to that account instead of creating a duplicate (email addresses
  are treated as verified because Google verifies them) — but only when the
  existing account has no TOTP device requiring verification. If 2FA is
  enabled on the target account, Google sign-in is refused and the user is
  redirected to the normal login so they can complete TOTP verification.
* Secrets are never logged here or anywhere in the OAuth flow.
"""

from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.models import EmailAddress
from allauth.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib import messages
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
        """Link Google identities to existing local accounts (no duplicates).

        Fires before allauth decides to sign up. When the verified Google
        email matches an existing account we connect the social account to
        that user and authenticate them — unless 2FA is enabled, in which
        case we bounce to the standard login so the TOTP challenge runs.
        """
        if sociallogin.is_existing:
            return

        email = (sociallogin.account.extra_data.get("email") or "").lower()
        if not email:
            return

        email_address = EmailAddress.objects.filter(email__iexact=email).first()
        user = email_address.user if email_address else None
        if user is None:
            # Fall back to the auth user table (allauth only mirrors
            # verified addresses into EmailAddress on first use).
            from django.contrib.auth import get_user_model

            User = get_user_model()
            user = User.objects.filter(email__iexact=email).first()

        if user is None:
            return  # genuinely new user → normal signup flow

        from django_otp.plugins.otp_totp.models import TOTPDevice

        has_2fa = (
            user.is_authenticated
            and TOTPDevice.objects.filter(user=user, confirmed=True).exists()
        )
        if has_2fa:
            # Refuse silent social bypass of TOTP; send them through the
            # password + 2FA login flow instead.
            messages.add_message(
                request,
                messages.INFO,
                "This account uses two-factor authentication. Sign in with "
                "your password to complete verification.",
            )
            raise ImmediateHttpResponse(redirect("/login?social=2fa"))

        # Link identity to the existing account and continue sign-in.
        sociallogin.connect(request, user)
