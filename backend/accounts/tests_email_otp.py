"""Tests for first-time Google sign-in email OTP verification.

Covers the full flow: new Google account → pending verification → OTP email
→ verify → JWT. Also enforces the security limits (expiry, single-use,
attempt cap, resend cooldown) and regression-checks that existing
username/password login, JWT refresh, and TOTP protection are unchanged.
"""

from datetime import timedelta
from unittest import mock
from urllib.parse import parse_qs, unquote, urlparse

from django.core import mail
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from .models import AuditLog, EmailOTPVerification, User


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
            # Start through the real view so the signed state is valid.
            start_url = client.get("/api/auth/google/start/").data["authorize_url"]
            # Parse properly — the signed state contains URL-encoded chars.
            state = parse_qs(urlparse(start_url).query)["state"][0]
            return client.get(
                reverse("accounts:google-callback"),
                {"code": "auth-code", "state": state},
            )


def _token_from_redirect(response) -> str:
    """Extract the verification token from the callback's redirect URL."""
    query = parse_qs(urlparse(response.url).query)
    return unquote(query["token"][0])


def _code_from_outbox(index: int = -1) -> str:
    """Pull the 6-digit OTP out of the delivered email body."""
    body = mail.outbox[index].body
    digits = "".join(ch for ch in body if ch.isdigit())
    # The body contains the code and the expiry minutes (10); the code is
    # the 6-digit run, so take digits beyond the "10".
    code = digits.replace("10", "", 1) if len(digits) > 6 else digits
    return code[:6]


class FirstTimeGoogleLoginTests(APITestCase):
    """New Google email → REQUESTER account + OTP, never an instant JWT."""

    def setUp(self):
        self.client = APIClient()
        self.email = "new.user@gmail.com"

    def test_first_login_creates_requester_and_redirects_to_otp(self):
        response = _oauth_callback(self.client, self.email)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/auth/verify-otp?token=", response.url)

        user = User.objects.get(email=self.email)
        self.assertEqual(user.role, "REQUESTER")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

        session = EmailOTPVerification.objects.get(user=user)
        self.assertIsNone(session.verified_at)
        self.assertEqual(session.attempts, 0)
        self.assertEqual(session.resend_count, 0)

    def test_first_login_does_not_issue_jwt(self):
        response = _oauth_callback(self.client, self.email)
        self.assertIn("/auth/verify-otp", response.url)
        self.assertNotIn("/auth/callback", response.url)
        # No token fragment is handed to the browser for new users.
        self.assertNotIn("access=", response.url)

    def test_otp_email_is_sent(self):
        _oauth_callback(self.client, self.email)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.email, mail.outbox[0].to)
        self.assertIn("SAS RESERVE", mail.outbox[0].from_email)

    def test_otp_stored_hashed_not_plaintext(self):
        _oauth_callback(self.client, self.email)
        session = EmailOTPVerification.objects.get(
            user=User.objects.get(email=self.email)
        )
        # Django password hashes have a recognizable prefix; raw 6-digit OTP
        # would be all digits.
        self.assertFalse(session.otp_hash.isdigit())
        self.assertTrue(session.otp_hash.startswith(("pbkdf2_", "argon2", "bcrypt")))

    def test_account_created_audit_event(self):
        _oauth_callback(self.client, self.email)
        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditLog.Action.GOOGLE_FIRST_ACCOUNT
            ).exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(action=AuditLog.Action.OTP_SENT).exists()
        )


class OtpVerificationTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.email = "verify.user@gmail.com"

    def _fresh_session(self):
        """Run the callback and return (token, otp) for the new session."""
        response = _oauth_callback(self.client, self.email)
        token = _token_from_redirect(response)
        otp = _code_from_outbox()
        return token, otp

    def _verify(self, token: str, otp: str):
        return self.client.post(
            "/api/auth/google/verify-otp/",
            {"verification_token": token, "otp": otp},
        )

    def test_correct_otp_issues_jwt(self):
        token, otp = self._fresh_session()
        response = self._verify(token, otp)
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["user"]["email"], self.email)
        self.assertEqual(response.data["user"]["role"], "REQUESTER")
        self.assertTrue(
            AuditLog.objects.filter(action=AuditLog.Action.OTP_VERIFIED).exists()
        )

    def test_incorrect_otp_fails(self):
        token, otp = self._fresh_session()
        wrong = "000000" if otp != "000000" else "000001"
        response = self._verify(token, wrong)
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("access", response.data)
        self.assertNotIn("refresh", response.data)
        self.assertTrue(
            AuditLog.objects.filter(action=AuditLog.Action.OTP_FAILED).exists()
        )

    def test_otp_single_use(self):
        token, otp = self._fresh_session()
        first = self._verify(token, otp)
        self.assertEqual(first.status_code, 200)
        second = self._verify(token, otp)
        self.assertEqual(second.status_code, 400)
        self.assertEqual(second.data.get("code"), "already_verified")

    def test_expired_otp_rejected(self):
        token, otp = self._fresh_session()
        EmailOTPVerification.objects.filter(user__email=self.email).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        response = self._verify(token, otp)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data.get("code"), "expired")

    def test_five_attempts_then_locked(self):
        token, _ = self._fresh_session()
        for i in range(5):
            wrong = f"{i:06d}"
            if wrong == "000000":
                continue
            response = self._verify(token, wrong)
            self.assertEqual(response.status_code, 400)
        response = self._verify(token, "999999")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data.get("code"), "too_many_attempts")

    def test_unknown_token_rejected(self):
        self._fresh_session()
        response = self._verify("bogus-token", "123456")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data.get("code"), "invalid_token")

    def test_otp_and_token_never_returned(self):
        token, otp = self._fresh_session()
        response = self._verify(token, "000000")
        body = str(response.data)
        self.assertNotIn(otp, body)
        self.assertNotIn(token, body)


class OtpResendTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.email = "resend.user@gmail.com"
        response = _oauth_callback(self.client, self.email)
        self.token = _token_from_redirect(response)

    def _resend(self):
        return self.client.post(
            "/api/auth/google/resend-otp/", {"verification_token": self.token}
        )

    def _bypass_cooldown(self):
        EmailOTPVerification.objects.filter(user__email=self.email).update(
            last_sent_at=timezone.now() - timedelta(seconds=120)
        )

    def test_resend_sends_new_code(self):
        self._bypass_cooldown()
        outbox_before = len(mail.outbox)
        response = self._resend()
        self.assertEqual(response.status_code, 200)
        self.assertIn("sent", response.data["detail"].lower())
        self.assertEqual(len(mail.outbox), outbox_before + 1)
        self.assertTrue(
            AuditLog.objects.filter(action=AuditLog.Action.OTP_RESENT).exists()
        )

    def test_resend_cooldown_enforced(self):
        # The initial send from setUp is inside the cooldown window.
        response = self._resend()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data.get("code"), "resend_cooldown")

    def test_resend_invalidates_previous_otp(self):
        old_code = _code_from_outbox()
        self._bypass_cooldown()
        self._resend()
        new_code = _code_from_outbox()

        if old_code != new_code:
            old = self.client.post(
                "/api/auth/google/verify-otp/",
                {"verification_token": self.token, "otp": old_code},
            )
            self.assertEqual(old.status_code, 400)

        good = self.client.post(
            "/api/auth/google/verify-otp/",
            {"verification_token": self.token, "otp": new_code},
        )
        self.assertEqual(good.status_code, 200)

    def test_resend_limit(self):
        # The IP-level throttle (3 per 10 min) is exercised separately in
        # tests_security.py; here we verify the per-session budget (5) with
        # the network throttle disabled so both layers are covered.
        from unittest.mock import patch

        with patch(
            "accounts.oauth_views.OtpResendThrottle.allow_request",
            return_value=True,
        ):
            for _ in range(5):
                self._bypass_cooldown()
                response = self._resend()
                self.assertEqual(response.status_code, 200)
            self._bypass_cooldown()
            response = self._resend()
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.data.get("code"), "resend_exhausted")


class ExistingUserFlowTests(APITestCase):
    """Existing accounts: no OTP, TOTP intact, no duplicates."""

    def setUp(self):
        self.client = APIClient()

    def test_existing_user_skips_email_otp(self):
        User.objects.create_user(
            username="existing",
            password="pass1234!",
            email="existing.user@gmail.com",
        )
        response = _oauth_callback(self.client, "existing.user@gmail.com")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/auth/callback", response.url)  # token handoff as before
        self.assertFalse(
            EmailOTPVerification.objects.exists(),
            "Existing users must never get a first-time OTP session",
        )

    def test_duplicate_email_not_created(self):
        User.objects.create_user(
            username="original",
            password="pass1234!",
            email="dup.user@gmail.com",
        )
        _oauth_callback(self.client, "dup.user@gmail.com")
        self.assertEqual(User.objects.filter(email="dup.user@gmail.com").count(), 1)

    def test_totp_user_still_requires_totp(self):
        from . import twofa

        user = User.objects.create_user(
            username="totpuser",
            password="pass1234!",
            email="totp.user@gmail.com",
        )
        twofa.start_setup(user)
        from django_otp.plugins.otp_totp.models import TOTPDevice

        TOTPDevice.objects.filter(user=user).update(confirmed=True)
        response = _oauth_callback(self.client, "totp.user@gmail.com")
        self.assertIn("google_error=twofa_required", response.url)

    def test_google_never_grants_admin(self):
        _oauth_callback(self.client, "wouldbe.admin@gmail.com")
        user = User.objects.get(email="wouldbe.admin@gmail.com")
        self.assertEqual(user.role, "REQUESTER")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)


class PendingAccountSecurityTests(APITestCase):
    """A pending (unverified) account cannot authenticate by other means."""

    def setUp(self):
        self.client = APIClient()
        _oauth_callback(self.client, "pending.user@gmail.com")
        self.user = User.objects.get(email="pending.user@gmail.com")

    def test_password_login_blocked_while_pending(self):
        self.user.set_password("somepassword1!")
        self.user.save()
        response = self.client.post(
            "/api/auth/login/",
            {"username": self.user.username, "password": "somepassword1!"},
        )
        self.assertEqual(response.status_code, 400)

    def test_session_state_is_pending(self):
        session = EmailOTPVerification.objects.get(user=self.user)
        self.assertIsNotNone(session.otp_hash)
        self.assertIsNone(session.verified_at)


class RegressionTests(APITestCase):
    """Existing flows unaffected by the OTP system."""

    def setUp(self):
        self.client = APIClient()

    def test_password_login_still_works(self):
        User.objects.create_user(
            username="reguser", password="pass1234!", email="reg@school.edu"
        )
        response = self.client.post(
            "/api/auth/login/", {"username": "reguser", "password": "pass1234!"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)

    def test_jwt_refresh_still_works(self):
        User.objects.create_user(
            username="refresher", password="pass1234!", email="refresh@school.edu"
        )
        login = self.client.post(
            "/api/auth/login/", {"username": "refresher", "password": "pass1234!"}
        )
        response = self.client.post(
            "/api/auth/refresh/", {"refresh": login.data["refresh"]}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)

    def test_email_failure_handled_safely(self):
        with mock.patch(
            "accounts.email_otp.EmailMultiAlternatives.send",
            side_effect=ConnectionError("smtp down"),
        ):
            response = _oauth_callback(self.client, "sendfail@gmail.com")
        # Friendly redirect — no crash, no internal error leaked.
        self.assertEqual(response.status_code, 302)
        self.assertIn("google_error=otp_send_failed", response.url)
        # The pending session was rolled back so no dead session lingers.
        self.assertFalse(
            EmailOTPVerification.objects.filter(
                user__email="sendfail@gmail.com"
            ).exists()
        )
