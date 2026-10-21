"""Google OAuth registration-flow tests.

The registration page reuses the shared ``/api/auth/google/`` implementation.
The signed ``intent`` issued by ``google_start`` decides which operation runs:

* ``intent=login`` only authenticates an existing account (never creates one);
* ``intent=register`` creates the local account from Google's *verified*
  identity, links it through the django-allauth ``SocialAccount`` table, and
  applies the same approval policy as the password registration endpoint
  (unapproved / view-only until an administrator approves it).

These tests drive the real start + callback endpoints with Google mocked,
covering: signed-intent handling, account creation, approval policy, no
duplicate accounts, no insecure email-based linking, denied consent / provider
errors, unverified email, and external-organization approval (which Google
never bypasses).
"""

from unittest import mock
from urllib.parse import parse_qs, unquote, urlencode, urlparse

from allauth.socialaccount.models import SocialAccount
from django.core.signing import TimestampSigner
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from .models import AuditLog, Organization, User

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
    **extra,
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
    query.update(extra)

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
    return {
        key: unquote(value)
        for key, value in (
            pair.split("=", 1) for pair in urlparse(response.url).fragment.split("&")
        )
    }


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

    def test_expired_state_is_rejected(self):
        # An expired signature is refused before the (untrusted) intent is
        # read, so the error goes to the safe default: the login page.
        state = _start(self.client, intent="register")
        with mock.patch("accounts.oauth_views.STATE_MAX_AGE_SECONDS", -1):
            response = _callback(self.client, state)
        self.assertTrue(response.url.startswith(f"{ORIGIN}/login"))
        self.assertIn("google_error=invalid_state", response.url)
        self.assertFalse(User.objects.filter(email=EMAIL).exists())

    def test_token_exchange_failure_does_not_create_account(self):
        state = _start(self.client, intent="register")
        response = _callback(self.client, state, fail_token=True)
        self.assertTrue(response.url.startswith(f"{ORIGIN}/register"))
        self.assertIn("google_error=token_exchange_failed", response.url)
        self.assertFalse(User.objects.filter(email=EMAIL).exists())


class GoogleRegistrationFlowTests(APITestCase):
    """Registering with Google creates an account; logging in never does."""

    def setUp(self):
        self.client = APIClient()

    def test_new_google_identity_registers_an_account(self):
        response = _callback(self.client, _start(self.client, intent="register"))

        # Registration success returns to the login page (registration never
        # authenticates, exactly like the password flow) — no JWTs.
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(f"{ORIGIN}/login"))
        self.assertIn("registered=google", response.url)
        self.assertNotIn("access=", response.url)

        user = User.objects.get(email=EMAIL)
        self.assertEqual(user.first_name, "Juan")
        self.assertEqual(user.last_name, "Dela Cruz")
        self.assertEqual(user.username, "new.grad")
        self.assertEqual(user.role, User.Role.REQUESTER)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        # Same approval policy as a normal registration: unapproved until an
        # administrator approves it.
        self.assertFalse(user.is_active)
        self.assertFalse(user.is_approved)
        self.assertTrue(user.is_view_only)
        # Google is the account's only credential.
        self.assertFalse(user.has_usable_password())
        self.assertTrue(
            SocialAccount.objects.filter(
                provider=PROVIDER, uid=SUB, user=user
            ).exists()
        )

    def test_google_registration_is_audited(self):
        _callback(self.client, _start(self.client, intent="register"))
        user = User.objects.get(email=EMAIL)
        actions = set(
            AuditLog.objects.filter(actor=user).values_list("action", flat=True)
        )
        self.assertIn(AuditLog.Action.REGISTER, actions)
        self.assertIn(AuditLog.Action.GOOGLE_FIRST_ACCOUNT, actions)

    def test_new_google_identity_on_login_is_still_refused(self):
        response = _callback(self.client, _start(self.client))  # login intent
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(f"{ORIGIN}/login"))
        self.assertIn("google_error=no_account_found", response.url)
        self.assertNotIn("access=", response.url)
        self.assertFalse(User.objects.filter(email=EMAIL).exists())
        self.assertFalse(SocialAccount.objects.exists())

    def test_login_intent_cannot_be_turned_into_registration_by_a_query_param(self):
        # The intent comes from the signed state only; a client-supplied
        # ``intent`` parameter is ignored.
        state = _start(self.client)  # login intent
        response = _callback(self.client, state, intent="register")
        self.assertIn("google_error=no_account_found", response.url)
        self.assertFalse(User.objects.filter(email=EMAIL).exists())

    def test_registered_google_account_signs_in_with_google(self):
        _callback(self.client, _start(self.client, intent="register"))

        response = _callback(self.client, _start(self.client))  # login intent
        self.assertEqual(response.status_code, 302)
        self.assertIn("/auth/callback", response.url)
        self.assertIn("access", _tokens(response))
        self.assertEqual(User.objects.filter(email=EMAIL).count(), 1)
        self.assertEqual(SocialAccount.objects.count(), 1)

    def test_repeated_registration_requests_do_not_duplicate_the_account(self):
        first = _callback(self.client, _start(self.client, intent="register"))
        self.assertIn("registered=google", first.url)

        second = _callback(self.client, _start(self.client, intent="register"))
        self.assertIn("google_error=account_exists", second.url)
        self.assertNotIn("access=", second.url)
        self.assertEqual(User.objects.filter(email=EMAIL).count(), 1)
        self.assertEqual(SocialAccount.objects.count(), 1)

    def test_username_collision_gets_a_unique_username(self):
        User.objects.create_user(username="new.grad", password="pass1234!")
        _callback(self.client, _start(self.client, intent="register"))

        user = User.objects.get(email=EMAIL)
        self.assertNotEqual(user.username, "new.grad")
        self.assertEqual(User.objects.filter(username=user.username).count(), 1)

    def test_existing_password_account_is_never_auto_linked_on_register(self):
        existing = User.objects.create_user(
            username="existing", email=EMAIL, password="pass1234!"
        )
        response = _callback(self.client, _start(self.client, intent="register"))
        self.assertTrue(response.url.startswith(f"{ORIGIN}/login"))
        self.assertIn("google_error=email_registered", response.url)
        self.assertNotIn("access=", response.url)
        self.assertEqual(User.objects.filter(email=EMAIL).count(), 1)
        self.assertFalse(
            SocialAccount.objects.filter(provider=PROVIDER, user=existing).exists()
        )

    def test_existing_password_account_is_never_auto_linked_on_login(self):
        User.objects.create_user(username="existing", email=EMAIL, password="pass1234!")
        response = _callback(self.client, _start(self.client))  # login intent
        self.assertTrue(response.url.startswith(f"{ORIGIN}/login"))
        self.assertIn("google_error=email_registered", response.url)
        self.assertNotIn("access=", response.url)
        self.assertFalse(SocialAccount.objects.exists())

    def test_legacy_passwordless_google_account_can_still_sign_in(self):
        # An account originally created through Google (no usable password)
        # may adopt the verified identity on sign-in so its owner is not
        # locked out by the no-email-linking rule.
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
            userinfo={
                "sub": "google-sub-unverified",
                "email": "unverified@gmail.com",
                "email_verified": False,
            },
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
    """Google sign-up follows the existing approval/authorization workflow."""

    def setUp(self):
        self.client = APIClient()

    def _register_google_user(self) -> str:
        """Register through Google, then sign in through Google for JWTs."""
        registered = _callback(self.client, _start(self.client, intent="register"))
        self.assertIn("registered=google", registered.url)

        signed_in = _callback(self.client, _start(self.client))
        access = _tokens(signed_in)["access"]
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

    def test_new_google_account_is_view_only_until_approved(self):
        self._register_google_user()

        me = self.client.get("/api/auth/me/")
        self.assertEqual(me.status_code, 200)
        self.assertFalse(me.data["is_approved"])
        self.assertTrue(me.data["is_view_only"])

        # A state-changing request is refused by the existing permission class.
        response = self._register_external_organization()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data.get("code"), "account_not_approved")
        # Only the seeded internal organizations exist — nothing was registered.
        self.assertFalse(
            Organization.objects.filter(
                organization_type="SCHOOL_UNIVERSITY"
            ).exists()
        )

    def test_approved_google_account_can_complete_its_affiliation(self):
        self._register_google_user()
        user = User.objects.get(email=EMAIL)
        user.is_active = True
        user.save(update_fields=["is_active"])
        self.client.force_authenticate(user)

        response = self._register_external_organization()
        self.assertEqual(response.status_code, 200, response.data)

        user.refresh_from_db()
        self.assertEqual(user.affiliation, "EXTERNAL_ORGANIZATION")
        organization = user.organization_ref
        self.assertIsNotNone(organization)
        self.assertEqual(
            organization.verification_status, Organization.VerificationStatus.PENDING
        )
        self.assertFalse(user.can_create_reservations)

    def test_google_user_cannot_self_approve_organization(self):
        self._register_google_user()
        user = User.objects.get(email=EMAIL)
        user.is_active = True
        user.save(update_fields=["is_active"])
        self.client.force_authenticate(user)

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
