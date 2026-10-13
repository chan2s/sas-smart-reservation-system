"""Google OAuth registration-flow tests.

The registration page reuses the shared ``/api/auth/google/`` implementation
and adds two behaviors:

* a signed ``intent`` that keeps OAuth errors on ``/register``;
* existing-account detection by Google's stable subject id (``sub``) via the
  django-allauth ``SocialAccount`` table — never by a client-supplied email.

These tests drive the real start + callback endpoints with Google mocked,
covering: signed-intent handling, new-account creation, existing-account
redirect to login, no duplicate accounts, no insecure email-based linking,
denied consent / provider errors, unverified email, and
external-organization approval (which Google never bypasses).
"""

from unittest import mock
from urllib.parse import parse_qs, urlencode, urlparse

from allauth.socialaccount.models import SocialAccount
from django.core.signing import TimestampSigner
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from .models import Organization, User

_OVERRIDES = dict(
    GOOGLE_CLIENT_ID="test-id",
    GOOGLE_CLIENT_SECRET="test-secret",
    DEBUG=True,
    ALLOW_DEV_TUNNELS=False,
    PUBLIC_FRONTEND_URL="http://localhost:5173",
)
ORIGIN = "http://localhost:5173"
EMAIL = "new.grad@gmail.com"
SUB = "google-sub-new-grad"
PROVIDER = "google"


def _start(client, intent=None):
    """Run google_start and return the signed state it issued."""
    query = {"frontend_origin": ORIGIN}
    if intent is not None:
        query["intent"] = intent
    with override_settings(**_OVERRIDES):
        response = client.get(f"/api/auth/google/start/?{urlencode(query)}")
    assert response.status_code == 200, response.data
    params = parse_qs(urlparse(response.data["authorize_url"]).query)
    return params["state"][0]


def _callback(
    client,
    state,
    *,
    userinfo=None,
    code="auth-code",
    provider_error=None,
    fail_token=False,
):
    """Drive the real callback through a mocked Google identity exchange."""
    userinfo = (
        userinfo
        if userinfo is not None
        else {
            "sub": SUB,
            "email": EMAIL,
            "email_verified": True,
            "given_name": "Juan",
            "family_name": "Dela Cruz",
        }
    )
    query = {"state": state}
    if code is not None:
        query["code"] = code
    if provider_error:
        query["error"] = provider_error

    import requests

    with override_settings(**_OVERRIDES):
        with mock.patch("accounts.oauth_views.requests.post") as mock_post, mock.patch(
            "accounts.oauth_views.requests.get"
        ) as mock_get:
            if fail_token:
                mock_post.side_effect = requests.RequestException("boom")
            else:
                mock_post.return_value.raise_for_status.return_value = None
                mock_post.return_value.json.return_value = {"access_token": "g-token"}
            mock_get.return_value.raise_for_status.return_value = None
            mock_get.return_value.json.return_value = userinfo
            return client.get(reverse("accounts:google-callback"), query)


def _tokens(response) -> dict:
    return dict(
        pair.split("=", 1) for pair in urlparse(response.url).fragment.split("&")
    )


class RegisterIntentStateTests(APITestCase):
    """The signed state carries the intent; raw input is never trusted."""

    def setUp(self):
        self.client = APIClient()

    def test_start_embeds_register_intent(self):
        state = _start(self.client, intent="register")
        data = TimestampSigner().unsign_object(state, max_age=600)
        self.assertEqual(data["i"], "register")

    def test_default_intent_is_login(self):
        state = _start(self.client)
        data = TimestampSigner().unsign_object(state, max_age=600)
        self.assertEqual(data["i"], "login")

    def test_unknown_intent_falls_back_to_login(self):
        state = _start(self.client, intent="../../create-organization")
        data = TimestampSigner().unsign_object(state, max_age=600)
        self.assertEqual(data["i"], "login")


class RegisterIntentErrorRedirectTests(APITestCase):
    """OAuth failures return to the page that started the flow."""

    def setUp(self):
        self.client = APIClient()

    def test_register_missing_code_redirects_to_register(self):
        state = _start(self.client, intent="register")
        response = _callback(self.client, state, code=None)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(f"{ORIGIN}/register"))
        self.assertIn("google_error=missing_code", response.url)
        self.assertNotIn("access=", response.url)

    def test_user_denied_consent_redirects_to_register(self):
        state = _start(self.client, intent="register")
        response = _callback(
            self.client, state, code=None, provider_error="access_denied"
        )
        self.assertTrue(response.url.startswith(f"{ORIGIN}/register"))
        self.assertIn("google_error=cancelled", response.url)

    def test_login_intent_errors_still_go_to_login(self):
        state = _start(self.client)  # default login intent
        response = _callback(self.client, state, code=None)
        self.assertTrue(response.url.startswith(f"{ORIGIN}/login"))
        self.assertIn("google_error=missing_code", response.url)

    def test_forged_state_redirects_to_login(self):
        response = _callback(self.client, "forged-state", code="x")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(f"{ORIGIN}/login"))
        self.assertIn("google_error=invalid_state", response.url)

    def test_token_exchange_failure_does_not_create_account(self):
        state = _start(self.client, intent="register")
        response = _callback(self.client, state, fail_token=True)
        self.assertTrue(response.url.startswith(f"{ORIGIN}/register"))
        self.assertIn("google_error=token_exchange_failed", response.url)
        self.assertFalse(User.objects.filter(email=EMAIL).exists())


class GoogleRegistrationFlowTests(APITestCase):
    """New registration and returning sign-in share one non-duplicating flow."""

    def setUp(self):
        self.client = APIClient()

    def test_new_account_created_as_requester_and_routed_to_callback(self):
        state = _start(self.client, intent="register")
        response = _callback(self.client, state)
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"{ORIGIN}/auth/callback", response.url)
        self.assertIn("access", _tokens(response))

        self.assertEqual(User.objects.filter(email=EMAIL).count(), 1)
        user = User.objects.get(email=EMAIL)
        self.assertEqual(user.role, "REQUESTER")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        # No affiliation yet — the SPA routes the account to onboarding.
        self.assertFalse(user.has_affiliation)
        # The Google identity is now associated via allauth's SocialAccount.
        self.assertTrue(
            SocialAccount.objects.filter(
                provider=PROVIDER, uid=SUB, user=user
            ).exists()
        )

    def test_existing_google_account_redirects_to_login_on_register(self):
        # First sign-in (login page) creates and associates the identity.
        first = _callback(self.client, _start(self.client))
        self.assertIn("/auth/callback", first.url)

        # The same Google identity then clicks "Continue with Google" on the
        # registration page: no sign-in, no duplicate — straight to login.
        response = _callback(self.client, _start(self.client, intent="register"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(f"{ORIGIN}/login"))
        self.assertIn("google_error=account_exists", response.url)
        self.assertNotIn("access=", response.url)
        self.assertEqual(User.objects.filter(email=EMAIL).count(), 1)
        self.assertEqual(SocialAccount.objects.count(), 1)

    def test_google_identity_signs_in_repeatedly_without_duplicates(self):
        _callback(self.client, _start(self.client))
        second = _callback(self.client, _start(self.client))
        self.assertIn("access", _tokens(second))
        self.assertEqual(User.objects.filter(email=EMAIL).count(), 1)
        self.assertEqual(SocialAccount.objects.count(), 1)

    def test_existing_password_account_is_never_auto_linked(self):
        existing = User.objects.create_user(
            username="existing", email=EMAIL, password="pass1234!"
        )
        # Registration must not duplicate or silently link the account.
        response = _callback(self.client, _start(self.client, intent="register"))
        self.assertTrue(response.url.startswith(f"{ORIGIN}/login"))
        self.assertIn("google_error=email_registered", response.url)
        self.assertNotIn("access=", response.url)
        self.assertEqual(User.objects.filter(email=EMAIL).count(), 1)
        self.assertFalse(
            SocialAccount.objects.filter(provider=PROVIDER, user=existing).exists()
        )

    def test_login_with_unlinked_password_email_is_also_refused(self):
        User.objects.create_user(username="existing", email=EMAIL, password="pass1234!")
        response = _callback(self.client, _start(self.client))  # login intent
        self.assertTrue(response.url.startswith(f"{ORIGIN}/login"))
        self.assertIn("google_error=email_registered", response.url)
        self.assertNotIn("access=", response.url)
        self.assertFalse(SocialAccount.objects.exists())

    def test_legacy_passwordless_google_account_can_still_sign_in(self):
        # An account originally created through Google (no usable password)
        # may adopt the verified identity on sign-in so its owner is not
        # locked out by the new no-email-linking rule.
        user = User.objects.create_user(username="legacy", email=EMAIL)
        self.assertFalse(user.has_usable_password())

        response = _callback(self.client, _start(self.client))  # login intent
        self.assertIn("access", _tokens(response))
        self.assertTrue(
            SocialAccount.objects.filter(provider=PROVIDER, uid=SUB, user=user).exists()
        )

    def test_legacy_passwordless_account_on_register_redirects_to_login(self):
        User.objects.create_user(username="legacy", email=EMAIL)
        response = _callback(self.client, _start(self.client, intent="register"))
        self.assertTrue(response.url.startswith(f"{ORIGIN}/login"))
        self.assertIn("google_error=account_exists", response.url)
        self.assertFalse(SocialAccount.objects.exists())

    def test_privileged_passwordless_account_is_not_adopted(self):
        # A privileged account without a password must never be adopted — the
        # Google email alone is not proof of authorization.
        user = User.objects.create_user(username="staffless", email=EMAIL)
        user.role = "STAFF"
        user.is_staff = True
        user.save(update_fields=["role", "is_staff"])

        response = _callback(self.client, _start(self.client))  # login intent
        self.assertTrue(response.url.startswith(f"{ORIGIN}/login"))
        self.assertIn("google_error=email_registered", response.url)
        self.assertFalse(SocialAccount.objects.exists())

    def test_unverified_google_email_is_rejected(self):
        state = _start(self.client, intent="register")
        response = _callback(
            self.client,
            state,
            userinfo={"email": "unverified@gmail.com", "email_verified": False},
        )
        self.assertTrue(response.url.startswith(f"{ORIGIN}/register"))
        self.assertIn("google_error=email_unverified", response.url)
        self.assertFalse(User.objects.filter(email="unverified@gmail.com").exists())

    def test_missing_subject_id_is_rejected(self):
        state = _start(self.client, intent="register")
        response = _callback(
            self.client,
            state,
            userinfo={"email": EMAIL, "email_verified": True},
        )
        self.assertIn("google_error=identity_failed", response.url)
        self.assertFalse(User.objects.filter(email=EMAIL).exists())


class GoogleRegistrationApprovalTests(APITestCase):
    """Google sign-up never bypasses organization verification or authorization."""

    def setUp(self):
        self.client = APIClient()

    def _register_google_user(self) -> str:
        response = _callback(self.client, _start(self.client, intent="register"))
        access = _tokens(response)["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        return access

    def _register_external_organization(self):
        return self.client.post(
            "/api/auth/affiliation/",
            {
                "affiliation": "EXTERNAL_ORGANIZATION",
                "organization_name": "Bayawan National High School",
                "organization_type": "SCHOOL_UNIVERSITY",
                "contact_person": "Juan Dela Cruz",
                "contact_email": "office@bnhs.edu",
                "contact_number": "09171234567",
                "address": "Bayawan City",
                "purpose": "Community seminar",
            },
            format="json",
        )

    def test_external_organization_stays_pending_and_blocks_reservations(self):
        self._register_google_user()
        response = self._register_external_organization()
        self.assertEqual(response.status_code, 200, response.data)

        user = User.objects.get(email=EMAIL)
        self.assertEqual(user.affiliation, "EXTERNAL_ORGANIZATION")
        organization = user.organization_ref
        self.assertIsNotNone(organization)
        self.assertEqual(
            organization.verification_status, Organization.VerificationStatus.PENDING
        )
        self.assertFalse(user.can_create_reservations)

        me = self.client.get("/api/auth/me/")
        self.assertEqual(me.status_code, 200)
        self.assertFalse(me.data["can_create_reservations"])
        self.assertTrue(me.data["reservation_block_reason"])

    def test_google_user_cannot_self_approve_organization(self):
        self._register_google_user()
        self.assertEqual(self._register_external_organization().status_code, 200)
        organization = User.objects.get(email=EMAIL).organization_ref

        response = self.client.post(
            f"/api/auth/organizations/{organization.pk}/verify/",
            {"action": "approve"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        organization.refresh_from_db()
        self.assertEqual(
            organization.verification_status, Organization.VerificationStatus.PENDING
        )
