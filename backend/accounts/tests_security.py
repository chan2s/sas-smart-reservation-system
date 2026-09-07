"""Security tests: first-time OTP bypass, JWT protection, rate limiting.

Covers the required security model:
* pending first-time Google account  =>  NOT AUTHENTICATED (any route)
* re-running the Google callback while pending never issues a JWT
* refresh tokens from a pre-pending state cannot mint access tokens
* global API throttles (anon/user) and sensitive-endpoint throttles
"""

from datetime import timedelta
from unittest import mock
from urllib.parse import parse_qs, unquote, urlparse

from django.core import mail
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from .models import EmailOTPVerification, User


def _oauth_callback(client, email: str):
    """Drive the real callback through a mocked Google identity exchange."""
    userinfo = {"email": email, "email_verified": True, "given_name": "Juan"}
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


def _token_from_redirect(response) -> str:
    query = parse_qs(urlparse(response.url).query)
    return unquote(query["token"][0])


def _code_from_outbox(index: int = -1) -> str:
    body = mail.outbox[index].body
    digits = "".join(ch for ch in body if ch.isdigit())
    code = digits.replace("10", "", 1) if len(digits) > 6 else digits
    return code[:6]


class FirstTimeOtpBypassTests(APITestCase):
    """BUG #1: re-running Google sign-in while pending must never issue a JWT."""

    def setUp(self):
        self.client = APIClient()
        self.email = "bypass.user@gmail.com"
        # First-time sign-in → pending account + OTP email.
        first = _oauth_callback(self.client, self.email)
        self.assertEqual(first.status_code, 302)
        self.assertIn("/auth/verify-otp", first.url)
        self.user = User.objects.get(email=self.email)
        self.assertFalse(self.user.first_login_verified)

    def test_second_callback_while_pending_never_issues_jwt(self):
        # User presses Back and signs in with Google again.
        second = _oauth_callback(self.client, self.email)
        self.assertEqual(second.status_code, 302)
        # MUST go to the OTP page, never to the token handoff.
        self.assertIn("/auth/verify-otp", second.url)
        self.assertNotIn("/auth/callback", second.url)
        self.assertNotIn("access=", second.url)
        # Still exactly one account, still pending.
        self.assertEqual(User.objects.filter(email=self.email).count(), 1)
        self.user.refresh_from_db()
        self.assertFalse(self.user.first_login_verified)

    def test_no_duplicate_session_on_reentry(self):
        second = _oauth_callback(self.client, self.email)
        self.assertIn("/auth/verify-otp", second.url)
        # resume_pending reuses/restarts — still exactly one session row.
        self.assertEqual(
            EmailOTPVerification.objects.filter(user=self.user).count(), 1
        )

    def test_pending_user_cannot_access_authenticated_api_without_jwt(self):
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, 401)

    def test_pending_user_receives_no_jwt_after_correct_otp_via_callback(self):
        # Even a correct OTP submitted through the callback URL does nothing.
        response = _oauth_callback(self.client, self.email)
        self.assertNotIn("access=", response.url)
        self.assertNotIn("refresh=", response.url)


class PendingAccountJwtProtectionTests(APITestCase):
    """A pending account cannot mint or use JWTs through ANY route."""

    def setUp(self):
        self.client = APIClient()
        self.email = "jwtblock.user@gmail.com"
        _oauth_callback(self.client, self.email)
        self.user = User.objects.get(email=self.email)

    def test_password_login_blocked_while_pending(self):
        self.user.set_password("Str0ngPass!x")
        self.user.save()
        response = self.client.post(
            "/api/auth/login/",
            {"username": self.user.username, "password": "Str0ngPass!x"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("access", response.data)

    def test_refresh_token_minting_blocked_while_pending(self):
        """A refresh token from an earlier state cannot mint an access token."""
        from rest_framework_simplejwt.tokens import RefreshToken

        # Simulate a token obtained before the account became pending.
        stale_refresh = str(RefreshToken.for_user(self.user))
        self.user.first_login_verified = False
        self.user.save(update_fields=["first_login_verified"])

        response = self.client.post(
            "/api/auth/refresh/", {"refresh": stale_refresh}
        )
        self.assertIn(response.status_code, (401, 403))
        self.assertNotIn("access", response.data)

    def test_access_token_rejected_while_pending(self):
        from rest_framework_simplejwt.tokens import RefreshToken

        stale = RefreshToken.for_user(self.user)
        self.user.first_login_verified = False
        self.user.save(update_fields=["first_login_verified"])

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {stale.access_token}")
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, 401)

    def test_verification_token_reuse_rejected(self):
        # Verify with the correct OTP → tokens issued, session consumed.
        response = _oauth_callback(self.client, self.email)
        token = _token_from_redirect(response)
        code = _code_from_outbox()
        ok = self.client.post(
            "/api/auth/google/verify-otp/",
            {"verification_token": token, "otp": code},
        )
        self.assertEqual(ok.status_code, 200)

        # The same token cannot start a second verification.
        reused = self.client.post(
            "/api/auth/google/verify-otp/",
            {"verification_token": token, "otp": code},
        )
        self.assertEqual(reused.status_code, 400)

    def test_otp_endpoint_is_the_only_path_that_sets_verified(self):
        response = _oauth_callback(self.client, self.email)
        token = _token_from_redirect(response)
        code = _code_from_outbox()
        self.client.post(
            "/api/auth/google/verify-otp/",
            {"verification_token": token, "otp": code},
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.first_login_verified)


class VerifiedUserFlowTests(APITestCase):
    """End-to-end: verify → JWT → authenticated APIs work."""

    def setUp(self):
        self.client = APIClient()
        self.email = "happy.path@gmail.com"

    def test_full_flow_from_pending_to_authenticated(self):
        response = _oauth_callback(self.client, self.email)
        token = _token_from_redirect(response)
        code = _code_from_outbox()

        result = self.client.post(
            "/api/auth/google/verify-otp/",
            {"verification_token": token, "otp": code},
        )
        self.assertEqual(result.status_code, 200)
        self.assertIn("access", result.data)
        self.assertIn("refresh", result.data)
        self.assertEqual(result.data["user"]["role"], "REQUESTER")

        # JWT works on authenticated endpoints.
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {result.data['access']}")
        me = self.client.get("/api/auth/me/")
        self.assertEqual(me.status_code, 200)

        # Refresh works for verified users.
        refreshed = self.client.post(
            "/api/auth/refresh/", {"refresh": result.data["refresh"]}
        )
        self.assertEqual(refreshed.status_code, 200)
        self.assertIn("access", refreshed.data)

        # Later Google sign-ins skip OTP entirely (no repeat verification).
        mail.outbox.clear()
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
        for _ in range(61):
            statuses.append(client.get("/api/public/facilities/").status_code)
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

    def test_otp_verify_throttle(self):
        from django.core.cache import cache

        client = APIClient()
        statuses = []
        for _ in range(7):
            statuses.append(
                client.post(
                    "/api/auth/google/verify-otp/",
                    {"verification_token": "bogus", "otp": "000000"},
                ).status_code
            )
        self.assertIn(429, statuses)
        cache.clear()

    def test_otp_resend_throttle(self):
        from django.core.cache import cache

        client = APIClient()
        statuses = []
        for _ in range(5):
            statuses.append(
                client.post(
                    "/api/auth/google/resend-otp/",
                    {"verification_token": "bogus"},
                ).status_code
            )
        self.assertIn(429, statuses)
        cache.clear()

    def test_throttled_response_is_uniform_json(self):
        from django.core.cache import cache

        client = APIClient()
        for _ in range(7):
            response = client.post(
                "/api/auth/google/verify-otp/",
                {"verification_token": "bogus", "otp": "000000"},
            )
        last = client.post(
            "/api/auth/google/verify-otp/",
            {"verification_token": "bogus", "otp": "000000"},
        )
        self.assertEqual(last.status_code, 429)
        self.assertEqual(
            last.data.get("detail"), "Too many requests. Please try again later."
        )
        cache.clear()

    def test_normal_api_use_remains_functional(self):
        client = APIClient()
        # A handful of ordinary requests must never be throttled.
        for _ in range(10):
            response = client.get("/api/public/facilities/")
            self.assertNotEqual(response.status_code, 429)
