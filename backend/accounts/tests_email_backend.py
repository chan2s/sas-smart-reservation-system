"""Tests for the Resend HTTPS email backend (accounts.email_backends).

These exercise the backend directly with ``requests`` mocked, so no network
call is made. They lock in the API contract (payload fields, HTML alternative,
cc/bcc/reply_to) and the failure semantics (never report a failed send as
successful; never log the API key).
"""

from unittest import mock

from django.core.mail import EmailMultiAlternatives
from django.test import SimpleTestCase, override_settings

from .email_backends import ResendEmailBackend, ResendEmailError

BACKEND = "accounts.email_backends.ResendEmailBackend"
API_KEY = "re_test_key_do_not_log"


def _message(**kwargs):
    defaults = dict(
        subject="Verify",
        body="Your code is 123456",
        from_email="SAS RESERVE <onboarding@resend.dev>",
        to=["dest@example.com"],
    )
    defaults.update(kwargs)
    return EmailMultiAlternatives(**defaults)


class ResendPayloadTests(SimpleTestCase):
    @override_settings(RESEND_API_KEY=API_KEY)
    @mock.patch("accounts.email_backends.requests.post")
    def test_sends_text_email_and_returns_count(self, mock_post):
        mock_post.return_value.status_code = 200
        sent = ResendEmailBackend(fail_silently=False).send_messages([_message()])

        self.assertEqual(sent, 1)
        mock_post.assert_called_once()
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["from"], "SAS RESERVE <onboarding@resend.dev>")
        self.assertEqual(payload["to"], ["dest@example.com"])
        self.assertEqual(payload["subject"], "Verify")
        self.assertEqual(payload["text"], "Your code is 123456")

    @override_settings(RESEND_API_KEY=API_KEY)
    @mock.patch("accounts.email_backends.requests.post")
    def test_includes_html_alternatives_cc_bcc_and_reply_to(self, mock_post):
        mock_post.return_value.status_code = 200
        message = _message(
            cc=["cc@example.com"],
            bcc=["bcc@example.com"],
            reply_to=["reply@example.com"],
        )
        message.attach_alternative("<p>Your code is 123456</p>", "text/html")

        ResendEmailBackend(fail_silently=False).send_messages([message])

        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["html"], "<p>Your code is 123456</p>")
        self.assertEqual(payload["cc"], ["cc@example.com"])
        self.assertEqual(payload["bcc"], ["bcc@example.com"])
        self.assertEqual(payload["reply_to"], ["reply@example.com"])

    @override_settings(RESEND_API_KEY=API_KEY)
    @mock.patch("accounts.email_backends.requests.post")
    def test_authorization_header_carries_key_and_timeout_is_set(self, mock_post):
        mock_post.return_value.status_code = 200
        ResendEmailBackend(fail_silently=False).send_messages([_message()])

        headers = mock_post.call_args.kwargs["headers"]
        self.assertEqual(headers["Authorization"], f"Bearer {API_KEY}")
        self.assertGreater(mock_post.call_args.kwargs["timeout"], 0)
        self.assertEqual(
            mock_post.call_args.args[0], "https://api.resend.com/emails"
        )


class ResendErrorTests(SimpleTestCase):
    @override_settings(RESEND_API_KEY="")
    def test_missing_api_key_raises(self):
        with self.assertRaises(ResendEmailError):
            ResendEmailBackend(fail_silently=False).send_messages([_message()])

    @override_settings(RESEND_API_KEY="")
    def test_missing_api_key_fail_silently_returns_zero(self):
        sent = ResendEmailBackend(fail_silently=True).send_messages([_message()])
        self.assertEqual(sent, 0)

    @override_settings(RESEND_API_KEY=API_KEY)
    @mock.patch("accounts.email_backends.requests.post")
    def test_api_error_raises_without_leaking_key(self, mock_post):
        mock_post.return_value.status_code = 422
        mock_post.return_value.json.return_value = {"message": "Invalid from"}

        with self.assertRaises(ResendEmailError) as ctx:
            ResendEmailBackend(fail_silently=False).send_messages([_message()])

        self.assertEqual(ctx.exception.status_code, 422)
        # Neither the API key nor the OTP body may appear in the error.
        self.assertNotIn(API_KEY, str(ctx.exception))
        self.assertNotIn("123456", str(ctx.exception))


    @override_settings(RESEND_API_KEY=API_KEY)
    @mock.patch("accounts.email_backends.requests.post")
    def test_api_error_fail_silently_logs_without_leaking_key(self, mock_post):
        mock_post.return_value.status_code = 422
        mock_post.return_value.json.return_value = {"message": "Invalid from"}

        with self.assertLogs("accounts.email_backends", level="WARNING") as logs:
            sent = ResendEmailBackend(fail_silently=True).send_messages([_message()])

        self.assertEqual(sent, 0)
        self.assertNotIn(API_KEY, str(logs.output))
        self.assertNotIn("123456", str(logs.output))

    @override_settings(RESEND_API_KEY=API_KEY)
    @mock.patch("accounts.email_backends.requests.post")
    def test_api_error_fail_silently_returns_zero(self, mock_post):
        mock_post.return_value.status_code = 500
        mock_post.return_value.json.side_effect = ValueError("not json")

        sent = ResendEmailBackend(fail_silently=True).send_messages([_message()])
        self.assertEqual(sent, 0)

    @override_settings(RESEND_API_KEY=API_KEY)
    @mock.patch("accounts.email_backends.requests.post")
    def test_transport_error_raises(self, mock_post):
        import requests

        mock_post.side_effect = requests.Timeout("timed out")
        with self.assertRaises(ResendEmailError):
            ResendEmailBackend(fail_silently=False).send_messages([_message()])
