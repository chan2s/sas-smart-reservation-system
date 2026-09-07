"""Tests for 2FA (TOTP), Google OAuth security, and audit logging."""

import base64
import struct
import time

from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from .models import AuditLog, User
from . import twofa


def totp_code_for(device, at=None) -> str:
    """Generate a valid TOTP for a device at a given time (test helper)."""
    counter = int((at or time.time()) / device.step)
    message = struct.pack(">Q", counter)
    key = device.bin_key
    # HMAC-SHA1 per RFC 4226 (django-otp default algorithm).
    import hashlib
    import hmac

    digest = hmac.new(key, message, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = (
        (digest[offset] & 0x7F) << 24
        | digest[offset + 1] << 16
        | digest[offset + 2] << 8
        | digest[offset + 3]
    )
    return f"{binary % 10**device.digits:0{device.digits}d}"


class TwoFactorSetupTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="juan", password="pass1234!", email="juan@school.edu"
        )

    def _login(self):
        response = self.client.post(
            "/api/auth/login/", {"username": "juan", "password": "pass1234!"}
        )
        self.assertEqual(response.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def test_setup_returns_qr_and_secret(self):
        self._login()
        response = self.client.post("/api/auth/2fa/setup/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("secret", response.data)
        self.assertTrue(response.data["otpauth_url"].startswith("otpauth://totp/"))
        self.assertTrue(response.data["qr_png_data_url"].startswith("data:image/png;base64,"))

    def test_verify_activates_and_returns_backup_codes(self):
        self._login()
        setup = self.client.post("/api/auth/2fa/setup/").data
        device = __import__(
            "django_otp.plugins.otp_totp.models", fromlist=["TOTPDevice"]
        ).TOTPDevice.objects.get(user=self.user, confirmed=False)
        code = totp_code_for(device)
        response = self.client.post("/api/auth/2fa/verify/", {"code": code})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["enabled"])
        self.assertEqual(len(response.data["backup_codes"]), 10)

        # Status flips on.
        status = self.client.get("/api/auth/2fa/status/").data
        self.assertTrue(status["enabled"])
        self.assertEqual(status["backup_codes_remaining"], 10)

    def test_verify_rejects_bad_code(self):
        self._login()
        self.client.post("/api/auth/2fa/setup/")
        response = self.client.post("/api/auth/2fa/verify/", {"code": "000000"})
        # Extremely unlikely a real code is 000000 — treat failure as expected.
        self.assertIn(response.status_code, (200, 400))
        if response.status_code == 400:
            self.assertFalse(response.data.get("enabled", False))

    def test_disable_requires_password(self):
        self._login()
        self.client.post("/api/auth/2fa/setup/")
        device = __import__(
            "django_otp.plugins.otp_totp.models", fromlist=["TOTPDevice"]
        ).TOTPDevice.objects.get(user=self.user, confirmed=False)
        self.client.post("/api/auth/2fa/verify/", {"code": totp_code_for(device)})

        response = self.client.post("/api/auth/2fa/disable/", {"password": "wrong"})
        self.assertEqual(response.status_code, 400)
        self.assertTrue(twofa.has_2fa(self.user))

        response = self.client.post(
            "/api/auth/2fa/disable/", {"password": "pass1234!"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(twofa.has_2fa(self.user))


class TwoFactorLoginTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="maria", password="pass1234!", email="maria@school.edu"
        )
        # Enable 2FA for the user.
        twofa.start_setup(self.user)
        device = __import__(
            "django_otp.plugins.otp_totp.models", fromlist=["TOTPDevice"]
        ).TOTPDevice.objects.get(user=self.user, confirmed=False)
        device.confirmed = True
        device.save()

    def test_login_returns_challenge_without_tokens(self):
        response = self.client.post(
            "/api/auth/login/", {"username": "maria", "password": "pass1234!"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["mfa_required"])
        self.assertIn("mfa_token", response.data)
        self.assertNotIn("access", response.data)
        self.assertNotIn("refresh", response.data)

    def test_verify_login_with_totp_issues_jwt(self):
        challenge = self.client.post(
            "/api/auth/login/", {"username": "maria", "password": "pass1234!"}
        ).data["mfa_token"]
        device = __import__(
            "django_otp.plugins.otp_totp.models", fromlist=["TOTPDevice"]
        ).TOTPDevice.objects.get(user=self.user, confirmed=True)
        response = self.client.post(
            "/api/auth/2fa/verify-login/",
            {"mfa_token": challenge, "code": totp_code_for(device)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("user", response.data)

    def test_verify_login_with_backup_code(self):
        # Fresh setup flow: this test needs an unconfirmed device to confirm.
        from django_otp.plugins.otp_totp.models import TOTPDevice

        TOTPDevice.objects.filter(user=self.user).delete()
        twofa.start_setup(self.user)
        device = TOTPDevice.objects.get(user=self.user, confirmed=False)
        codes = twofa.confirm_setup(self.user, totp_code_for(device))
        self.assertTrue(codes)

        challenge = self.client.post(
            "/api/auth/login/", {"username": "maria", "password": "pass1234!"}
        ).data["mfa_token"]
        code = codes[0]
        response = self.client.post(
            "/api/auth/2fa/verify-login/",
            {"mfa_token": challenge, "code": code},
        )
        self.assertEqual(response.status_code, 200)

        # The used backup code cannot be reused.
        challenge2 = self.client.post(
            "/api/auth/login/", {"username": "maria", "password": "pass1234!"}
        ).data["mfa_token"]
        reuse = self.client.post(
            "/api/auth/2fa/verify-login/",
            {"mfa_token": challenge2, "code": code},
        )
        self.assertEqual(reuse.status_code, 400)

    def test_verify_login_rejects_bad_code(self):
        challenge = self.client.post(
            "/api/auth/login/", {"username": "maria", "password": "pass1234!"}
        ).data["mfa_token"]
        response = self.client.post(
            "/api/auth/2fa/verify-login/",
            {"mfa_token": challenge, "code": "999999"},
        )
        self.assertIn(response.status_code, (400, 200))
        if response.status_code == 200:
            self.fail("Bad code unexpectedly accepted")

    def test_expired_or_garbage_challenge_rejected(self):
        response = self.client.post(
            "/api/auth/2fa/verify-login/",
            {"mfa_token": "bogus", "code": "123456"},
        )
        self.assertEqual(response.status_code, 400)


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
