"""Security tests: Google OAuth hardening, JWT protection, rate limiting.

Covers the required security model:
* "Continue with Google" only authenticates existing registered accounts —
  an unregistered Google identity is refused without creating anything,
  while an existing account receives JWTs directly (no OTP step exists)
* every callback error path redirects to the SPA, never leaks internals
* global API throttles (anon/user) and sensitive-endpoint throttles
"""

from unittest import mock
from urllib.parse import parse_qs, unquote, urlparse

from django.core import mail
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from .models import User


def _oauth_callback(client, email: str):
    """Drive the real callback through a mocked Google identity exchange."""
    userinfo = {
        "sub": f"google-sub-{email}",
        "email": email,
        "email_verified": True,
        "given_name": "Juan",
    }
    with override_settings(GOOGLE_CLIENT_ID="test-id", GOOGLE_CLIENT_SECRET="test-secret"):
        with mock.patch("accounts.oauth_views.requests.post") as mock_post, mock.patch(
            "accounts.oauth_views.requests.get"
        ) as mock_get:
            mock_post.return_value.status_code = 200
            mock_post.return_value.raise_for_status.return_value = None
            mock_post.return_value.json.return_value = {"access_token": "g-token"}
            mock_get.return_value.status_code = 200
            mock_get.return_value.raise_for_status.return_value = None
            mock_get.return_value.json.return_value = userinfo
            start_url = client.get("/api/auth/google/start/").data["authorize_url"]
            state = parse_qs(urlparse(start_url).query)["state"][0]
            return client.get(
                reverse("accounts:google-callback"),
                {"code": "auth-code", "state": state},
            )


def _fragment_tokens(response) -> dict:
    return dict(
        pair.split("=", 1)
        for pair in urlparse(response.url).fragment.split("&")
    )


def _make_google_user(email: str) -> User:
    """Create an existing, registered account reachable through Google.

    Under the no-auto-registration policy the callback can only sign into an
    account that already exists. A password-less REQUESTER (such as an
    account originally created through Google) is adoptable on sign-in, so
    these tests create the user the same way registration does — with an
    unusable password — and let the real callback link the identity.
    """
    return User.objects.create_user(
        username=f"gsignin_{email.split('@')[0]}", email=email
    )


class FirstTimeGoogleSignInTests(APITestCase):
    """Google sign-in authenticates existing accounts; it never registers."""

    def setUp(self):
        self.client = APIClient()
        self.email = "bypass.user@gmail.com"

    def test_unregistered_google_identity_is_refused_without_creating_account(self):
        first = _oauth_callback(self.client, self.email)
        self.assertEqual(first.status_code, 302)
        # Not created → bounced back to the login page with the clear
        # "no account found" message and no JWT in the redirect.
        self.assertIn("google_error=no_account_found", first.url)
        self.assertNotIn("access=", first.url)
        # No user (and no identity record) was created.
        self.assertEqual(User.objects.filter(email=self.email).count(), 0)

    def test_registered_google_account_receives_jwt_immediately(self):
        _make_google_user(self.email)
        first = _oauth_callback(self.client, self.email)
        self.assertEqual(first.status_code, 302)
        self.assertIn("/auth/callback", first.url)
        self.assertIn("access=", first.url)
        self.assertNotIn("verify-otp", first.url)
        # Adopting the verified identity never duplicates the account.
        self.assertEqual(User.objects.filter(email=self.email).count(), 1)
        user = User.objects.get(email=self.email)
        self.assertEqual(user.role, "REQUESTER")

    def test_second_callback_signs_in_without_duplicates(self):
        _make_google_user(self.email)
        _oauth_callback(self.client, self.email)
        second = _oauth_callback(self.client, self.email)
        self.assertEqual(second.status_code, 302)
        self.assertIn("/auth/callback", second.url)
        self.assertIn("access=", second.url)
        # Still exactly one account.
        self.assertEqual(User.objects.filter(email=self.email).count(), 1)

    def test_no_email_is_ever_sent(self):
        _oauth_callback(self.client, self.email)
        self.assertEqual(len(mail.outbox), 0)


class GoogleJwtProtectionTests(APITestCase):
    """JWTs issued by the callback authenticate; nothing else mints them."""

    def setUp(self):
        self.client = APIClient()
        self.email = "jwtblock.user@gmail.com"

    def test_callback_jwt_authenticates_the_existing_account(self):
        _make_google_user(self.email)
        response = _oauth_callback(self.client, self.email)
        tokens = _fragment_tokens(response)
        self.assertIn("access", tokens)
        self.assertIn("refresh", tokens)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        me = self.client.get("/api/auth/me/")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.data["email"], self.email)

    def test_inactive_account_token_is_view_only(self):
        """An inactive (not-approved) account's JWT authenticates for reads only."""
        from rest_framework_simplejwt.tokens import RefreshToken

        user = User.objects.create_user(
            username="inactive",
            email=self.email,
            is_active=False,
        )
        stale = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {stale.access_token}")
        # The token still authenticates so the account can see its own status.
        me = self.client.get("/api/auth/me/")
        self.assertEqual(me.status_code, 200)
        self.assertFalse(me.data["is_approved"])
        # A state-changing call with the same token is refused.
        blocked = self.client.patch(
            "/api/auth/me/", {"first_name": "Nope"}, format="json"
        )
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(blocked.data["code"], "account_not_approved")

    def test_password_login_of_google_linked_account_without_password(self):
        """A Google-linked account without a password cannot password-login."""
        _make_google_user(self.email)
        _oauth_callback(self.client, self.email)
        user = User.objects.get(email=self.email)
        self.assertFalse(user.has_usable_password())
        response = self.client.post(
            "/api/auth/login/",
            {"username": user.username, "password": "whatever"},
        )
        # 400 (validation) or 401 (authentication failure) — either way no
        # tokens may be issued.
        self.assertIn(response.status_code, (400, 401))
        self.assertNotIn("access", response.data)


class VerifiedUserFlowTests(APITestCase):
    """End-to-end: Google sign-in → JWT → authenticated APIs work."""

    def setUp(self):
        self.client = APIClient()
        self.email = "happy.path@gmail.com"

    def test_full_flow_from_google_to_authenticated_apis(self):
        _make_google_user(self.email)
        response = _oauth_callback(self.client, self.email)
        tokens = _fragment_tokens(response)
        self.assertIn("access", tokens)

        # JWT works on authenticated endpoints.
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        me = self.client.get("/api/auth/me/")
        self.assertEqual(me.status_code, 200)

        # Refresh works.
        refreshed = self.client.post(
            "/api/auth/refresh/", {"refresh": tokens["refresh"]}
        )
        self.assertEqual(refreshed.status_code, 200)
        self.assertIn("access", refreshed.data)

        # Later Google sign-ins keep working identically (idempotent).
        again = _oauth_callback(self.client, self.email)
        self.assertIn("/auth/callback", again.url)
        self.assertEqual(len(mail.outbox), 0)


class SecretKeyCheckTests(APITestCase):
    """BUG #2: short JWT signing key is detected."""

    def test_short_key_raises_check_warning(self):
        from accounts.apps import secret_key_length_check

        with override_settings(SECRET_KEY="short-key"):
            errors = secret_key_length_check(None)
        self.assertTrue(any(e.id == "sas.W001" for e in errors))

    def test_long_key_passes_check(self):
        from accounts.apps import secret_key_length_check

        with override_settings(SECRET_KEY="x" * 64):
            errors = secret_key_length_check(None)
        self.assertEqual(errors, [])


class ThrottlingTests(APITestCase):
    """BUG #3: global + endpoint-specific rate limits return uniform 429s."""

    def test_anonymous_global_throttle_hits_429(self):
        from django.core.cache import cache

        client = APIClient()
        statuses = []
        # /api/auth/google/ is AllowAny, so requests actually reach (and are
        # counted by) the global anon throttle — permission-protected views
        # 401 before the throttle runs.
        for _ in range(61):
            statuses.append(client.get("/api/auth/google/").status_code)
        self.assertIn(429, statuses)
        cache.clear()

    def test_auth_login_throttle(self):
        from django.core.cache import cache

        client = APIClient()
        statuses = []
        for _ in range(7):
            statuses.append(
                client.post(
                    "/api/auth/login/",
                    {"username": "nobody", "password": "wrongpass"},
                ).status_code
            )
        self.assertIn(429, statuses)
        cache.clear()

    def test_google_start_throttle(self):
        from django.core.cache import cache

        with override_settings(GOOGLE_CLIENT_ID="test-id", GOOGLE_CLIENT_SECRET="s"):
            client = APIClient()
            statuses = [client.get("/api/auth/google/start/").status_code for _ in range(12)]
        self.assertIn(429, statuses)
        cache.clear()

    def test_throttled_response_is_uniform_json(self):
        from django.core.cache import cache

        client = APIClient()
        credentials = {"username": "nobody", "password": "wrongpass"}
        for _ in range(7):
            client.post("/api/auth/login/", credentials)
        last = client.post("/api/auth/login/", credentials)
        self.assertEqual(last.status_code, 429)
        self.assertEqual(
            last.data.get("detail"), "Too many requests. Please try again later."
        )
        cache.clear()

    def test_normal_api_use_remains_functional(self):
        client = APIClient()
        # A handful of ordinary requests must never be throttled.
        for _ in range(10):
            response = client.get("/api/auth/google/")
            self.assertNotEqual(response.status_code, 429)
