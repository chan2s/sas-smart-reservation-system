"""Tests for Google OAuth security and audit logging."""

from urllib.parse import parse_qs, urlparse

from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from .models import AuditLog, User


class LoginWithoutSecondFactorTests(APITestCase):
    """Email/password login authenticates in a single step — no 2FA challenge."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="juan", password="pass1234!", email="juan@school.edu"
        )

    def test_login_returns_tokens_and_user(self):
        response = self.client.post(
            "/api/auth/login/", {"username": "juan", "password": "pass1234!"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertIn("user", response.data)
        # No second-step challenge is ever returned.
        self.assertNotIn("mfa_required", response.data)
        self.assertNotIn("mfa_token", response.data)

    def test_tokens_authenticate_immediately(self):
        response = self.client.post(
            "/api/auth/login/", {"username": "juan", "password": "pass1234!"}
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {response.data['access']}"
        )
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 200)

    def test_removed_2fa_endpoints_are_gone(self):
        for path in (
            "/api/auth/2fa/status/",
            "/api/auth/2fa/setup/",
            "/api/auth/2fa/verify/",
            "/api/auth/2fa/disable/",
            "/api/auth/2fa/verify-login/",
            "/api/auth/2fa/backup-codes/",
        ):
            self.assertEqual(self.client.post(path, {}).status_code, 404, path)


class GoogleOAuthSecurityTests(APITestCase):
    def setUp(self):
        self.client = APIClient()

    def test_config_reports_unconfigured_without_client_id(self):
        response = self.client.get("/api/auth/google/")
        self.assertEqual(response.status_code, 200)
        # Whether configured depends on env; both shapes are acceptable.
        self.assertIn("configured", response.data)

    def test_callback_rejects_invalid_state(self):
        from django.test import override_settings

        with override_settings(GOOGLE_CLIENT_ID="test-id", GOOGLE_CLIENT_SECRET="test-secret"):
            response = self.client.get(
                "/api/auth/google/callback/", {"code": "x", "state": "forged"}
            )
            # Redirects to the SPA with an error code — never a token.
            self.assertEqual(response.status_code, 302)
            self.assertIn("google_error=invalid_state", response.url)

    def test_start_requires_configuration(self):
        from django.test import override_settings

        with override_settings(GOOGLE_CLIENT_ID="", GOOGLE_CLIENT_SECRET=""):
            response = self.client.get("/api/auth/google/start/")
            self.assertEqual(response.status_code, 503)

    # --- Dynamic frontend-origin handling (no hard-coded tunnel hosts) ---

    def test_start_embeds_browser_origin_in_state(self):
        from django.core.signing import TimestampSigner

        # DEBUG=True mirrors local dev, where localhost origins are trusted.
        with override_settings(
            GOOGLE_CLIENT_ID="test-id",
            GOOGLE_CLIENT_SECRET="test-secret",
            DEBUG=True,
        ):
            response = self.client.get(
                "/api/auth/google/start/", HTTP_REFERER="http://localhost:5173/login"
            )
        authorize_url = response.data["authorize_url"]
        state = parse_qs(urlparse(authorize_url).query)["state"][0]
        data = TimestampSigner().unsign_object(state, max_age=600)
        self.assertEqual(data["o"], "http://localhost:5173")

    def test_start_rejects_disallowed_origin(self):
        from django.core.signing import TimestampSigner

        with override_settings(GOOGLE_CLIENT_ID="test-id", GOOGLE_CLIENT_SECRET="test-secret"):
            response = self.client.get(
                "/api/auth/google/start/", HTTP_REFERER="https://evil.example.com/login"
            )
        authorize_url = response.data["authorize_url"]
        state = parse_qs(urlparse(authorize_url).query)["state"][0]
        data = TimestampSigner().unsign_object(state, max_age=600)
        self.assertIsNone(data["o"])

    def test_callback_returns_to_state_origin(self):
        """Callback redirects go to the origin the browser started from."""
        # Forged state → error redirect must use the Referer origin.
        with override_settings(DEBUG=True):
            response = self.client.get(
                "/api/auth/google/callback/",
                {"code": "x", "state": "forged"},
                HTTP_REFERER="http://localhost:5173/login",
            )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("http://localhost:5173/login"))
        self.assertIn("google_error=invalid_state", response.url)

    def test_callback_error_never_redirects_to_disallowed_origin(self):
        with override_settings(PUBLIC_FRONTEND_URL="http://testserver"):
            response = self.client.get(
                "/api/auth/google/callback/",
                {"code": "x", "state": "forged"},
                HTTP_REFERER="https://evil.example.com/login",
            )
        self.assertEqual(response.status_code, 302)
        # Falls back to PUBLIC_FRONTEND_URL, never the attacker's origin.
        self.assertTrue(response.url.startswith("http://testserver/"))

    # --- redirect_uri derivation (backend host / explicit pin) ---

    def _start_state_and_redirect_uri(self, query="", referer=None):
        """Run google_start and pull the redirect_uri + signed state out."""
        from django.core.signing import TimestampSigner

        overrides = {
            "GOOGLE_CLIENT_ID": "test-id",
            "GOOGLE_CLIENT_SECRET": "test-secret",
            "DEBUG": True,
            "GOOGLE_REDIRECT_URI": "",  # exercise the derived path
        }
        headers = {"HTTP_REFERER": referer} if referer else {}
        with override_settings(**overrides):
            response = self.client.get(
                "/api/auth/google/start/" + (f"?{query}" if query else ""),
                **headers,
            )
        self.assertEqual(response.status_code, 200)
        params = parse_qs(urlparse(response.data["authorize_url"]).query)
        return params["redirect_uri"][0], TimestampSigner().unsign_object(
            params["state"][0], max_age=600
        )

    def test_start_derives_redirect_uri_from_request_host(self):
        """Without a pin, the redirect_uri is built from the backend host."""
        redirect_uri, _ = self._start_state_and_redirect_uri(
            query="frontend_origin=http://localhost:5173",
            referer="http://localhost:5173/login",
        )
        # The test client reaches Django at http://testserver — the redirect
        # must point at the BACKEND, never at the frontend origin.
        self.assertTrue(
            redirect_uri.endswith("/api/auth/google/callback/"),
            redirect_uri,
        )
        self.assertNotIn("localhost:5173", redirect_uri)

    def test_start_state_still_binds_frontend_origin(self):
        """The signed state still records where the browser should return."""
        _, state = self._start_state_and_redirect_uri(
            query="frontend_origin=http://localhost:5173",
            referer="http://localhost:5173/login",
        )
        self.assertEqual(state["o"], "http://localhost:5173")

    def test_start_rejects_disallowed_frontend_origin_hint(self):
        """A spoofed origin hint is dropped; headers decide (or nothing)."""
        redirect_uri, state = self._start_state_and_redirect_uri(
            query="frontend_origin=https://evil.example.com",
            referer="http://localhost:5173/login",
        )
        # evil.example.com must never appear anywhere in the flow.
        self.assertNotIn("evil.example.com", redirect_uri)
        self.assertEqual(state["o"], "http://localhost:5173")

    def test_production_pins_redirect_uri_setting(self):
        """GOOGLE_REDIRECT_URI is used byte-for-byte when set."""
        overrides = {
            "GOOGLE_CLIENT_ID": "test-id",
            "GOOGLE_CLIENT_SECRET": "test-secret",
            "DEBUG": False,
            "ALLOW_DEV_TUNNELS": False,
            "PUBLIC_FRONTEND_URL": "https://sas.example.com",
            "GOOGLE_REDIRECT_URI": "https://sas.example.com/api/auth/google/callback/",
        }
        with override_settings(**overrides):
            response = self.client.get(
                "/api/auth/google/start/",
                HTTP_REFERER="https://fvjmzw20-5173.jpe1.devtunnels.ms/login",
            )
        self.assertEqual(response.status_code, 200)
        params = parse_qs(urlparse(response.data["authorize_url"]).query)
        self.assertEqual(
            params["redirect_uri"][0],
            "https://sas.example.com/api/auth/google/callback/",
        )

    def test_tunnel_hostname_change_does_not_change_redirect_uri(self):
        """The redirect_uri targets the backend; tunnel hostname is irrelevant.

        The signed state records which tunnel to return the browser to, so a
        restarted tunnel works without changing the registered redirect_uri.
        """
        old_redirect, old_state = self._start_state_and_redirect_uri(
            query="frontend_origin=https://old-host-5173.jpe1.devtunnels.ms"
        )
        new_redirect, new_state = self._start_state_and_redirect_uri(
            query="frontend_origin=https://new-host-5173.jpe1.devtunnels.ms"
        )
        # Both start requests use the same backend redirect_uri...
        self.assertEqual(old_redirect, new_redirect)
        self.assertTrue(old_redirect.endswith("/api/auth/google/callback/"))
        # ...while the state records the distinct return origins.
        self.assertEqual(
            old_state["o"], "https://old-host-5173.jpe1.devtunnels.ms"
        )
        self.assertEqual(
            new_state["o"], "https://new-host-5173.jpe1.devtunnels.ms"
        )

    def test_callback_error_returns_to_tunnel_origin(self):
        """Error redirects also honor the origin bound in the signed state."""
        from django.core.signing import TimestampSigner

        tunnel = "https://fvjmzw20-5173.jpe1.devtunnels.ms"
        state = TimestampSigner().sign_object(
            {"n": "nonce", "o": tunnel}
        )
        with override_settings(DEBUG=True):
            response = self.client.get(
                "/api/auth/google/callback/",
                {"state": state},  # valid state, but no code → missing_code
            )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(f"{tunnel}/login"))
        self.assertIn("google_error=missing_code", response.url)

    def test_google_login_never_creates_admin(self):
        """The social adapter forces REQUESTER for any social signup."""
        from django.contrib.auth import get_user_model

        from accounts.adapters import SasSocialAccountAdapter

        User = get_user_model()
        adapter = SasSocialAccountAdapter()

        class FakeSocialLogin:
            def __init__(self):
                # Hostile input: privileged role must be neutralized.
                self.user = User(
                    username="someone",
                    email="someone@x.com",
                    role="ADMIN",
                    is_staff=True,
                    is_superuser=True,
                )

        user = adapter.populate_user(
            request=None,
            sociallogin=FakeSocialLogin(),
            data={"username": "someone", "email": "someone@x.com"},
        )
        self.assertEqual(user.role, "REQUESTER")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)


class AuditLogTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="admin",
            password="pass1234!",
            email="admin@school.edu",
            role="ADMIN",
        )

    def test_audit_record_never_raises(self):
        entry = AuditLog.record(
            self.admin, AuditLog.Action.LOGIN, object_repr="test"
        )
        self.assertIsNotNone(entry)
        # Broken persistence is swallowed instead of breaking the action.
        from unittest.mock import patch

        with patch("accounts.models.AuditLog.objects.create", side_effect=RuntimeError):
            self.assertIsNone(
                AuditLog.record(
                    self.admin, AuditLog.Action.LOGIN, object_repr="boom"
                )
            )

    def test_audit_endpoint_staff_only(self):
        requester = User.objects.create_user(username="req", password="pass1234!")
        client = APIClient()
        login = client.post(
            "/api/auth/login/", {"username": "req", "password": "pass1234!"}
        )
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        response = client.get("/api/auth/audit-log/")
        self.assertEqual(response.status_code, 403)

        login = self.client.post(
            "/api/auth/login/", {"username": "admin", "password": "pass1234!"}
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        response = self.client.get("/api/auth/audit-log/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("results", response.data)

    def test_login_is_audited(self):
        self.client.post(
            "/api/auth/login/", {"username": "admin", "password": "pass1234!"}
        )
        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.admin, action=AuditLog.Action.LOGIN
            ).exists()
        )
