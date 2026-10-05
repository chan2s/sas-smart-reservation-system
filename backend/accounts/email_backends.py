"""Resend HTTPS API email backend for Django.

Render's free tier blocks outbound SMTP (ports 25, 465, 587), so the previous
Gmail SMTP configuration times out in production. This backend posts messages
to Resend's HTTPS API instead, which travels over port 443 and is never
subject to SMTP egress filtering.

Configuration (environment / ``backend/.env``)::

    EMAIL_BACKEND=accounts.email_backends.ResendEmailBackend
    RESEND_API_KEY=re_...                       # never commit / log the value
    RESEND_FROM_EMAIL="SAS RESERVE <onboarding@resend.dev>"
    DEFAULT_FROM_EMAIL="SAS RESERVE <onboarding@resend.dev>"

Behaviour:

* Supports ordinary Django email objects: subject, text body, HTML
  alternatives, to/cc/bcc, from_email, and reply_to.
* Uses the already-installed ``requests`` dependency — no extra packages.
* Raises ``ResendEmailError`` on any API/transport failure unless the message
  was sent with ``fail_silently=True`` (Django's standard contract), so a
  failed send is never reported as success.
* Never logs the API key, the email body (which for OTP mail contains the
  code), or any other secret — only the HTTP status and the short error
  ``message`` field returned by Resend.
"""

import logging

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"

# Conservative HTTP timeout; Resend answers quickly and an OTP send must not
# hang a request thread. Connect + read are both covered by this value.
RESEND_TIMEOUT_SECONDS = 10


class ResendEmailError(Exception):
    """Raised when the Resend API rejects or cannot deliver a message.

    The message is safe to log: it never contains the API key or the email
    body. It carries ``status_code`` when Resend returned an HTTP response.
    """

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ResendEmailBackend(BaseEmailBackend):
    """Django email backend that sends through ``https://api.resend.com``."""

    def __init__(self, fail_silently: bool = False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_url = getattr(settings, "RESEND_API_URL", RESEND_API_URL)
        self.timeout = float(
            getattr(settings, "RESEND_TIMEOUT_SECONDS", RESEND_TIMEOUT_SECONDS)
        )

    # -- Django backend API -------------------------------------------------

    def send_messages(self, email_messages) -> int:
        """Send each message; return the number successfully accepted."""
        if not email_messages:
            return 0

        sent = 0
        for message in email_messages:
            if self._send_message(message):
                sent += 1
        return sent

    # -- Internals ----------------------------------------------------------

    def _send_message(self, message) -> bool:
        api_key = getattr(settings, "RESEND_API_KEY", "") or ""
        if not api_key:
            return self._fail(
                "RESEND_API_KEY is not configured; the Resend backend cannot "
                "send email."
            )

        recipients = [addr for addr in (message.to or []) if addr]
        if not recipients:
            # Nothing to do — matches Django's "no recipients, no send" rule.
            return False

        from_email = (
            getattr(message, "from_email", None)
            or getattr(settings, "RESEND_FROM_EMAIL", "")
            or getattr(settings, "DEFAULT_FROM_EMAIL", "")
        )
        if not from_email:
            return self._fail(
                "No sender configured (set RESEND_FROM_EMAIL or "
                "DEFAULT_FROM_EMAIL)."
            )

        payload = {
            "from": from_email,
            "to": recipients,
            "subject": message.subject or "",
            "text": message.body or "",
        }

        html_body = self._html_alternative(message)
        if html_body is not None:
            payload["html"] = html_body

        if message.cc:
            payload["cc"] = [addr for addr in message.cc if addr]
        if message.bcc:
            payload["bcc"] = [addr for addr in message.bcc if addr]

        reply_to = self._reply_to(message)
        if reply_to:
            payload["reply_to"] = reply_to

        if getattr(message, "extra_headers", None):
            # Forward custom headers as-is; Django validates them upstream.
            payload["headers"] = {
                str(key): str(value)
                for key, value in message.extra_headers.items()
            }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            # Ask for JSON so error parsing is deterministic.
            "Accept": "application/json",
        }

        try:
            response = requests.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            # Never surface the request object (it carries the auth header).
            return self._fail(
                f"Resend request failed ({type(exc).__name__})."
            )

        if response.status_code >= 400:
            detail = self._error_detail(response)
            return self._fail(
                f"Resend API rejected the email "
                f"(status={response.status_code}, error={detail}).",
                status_code=response.status_code,
            )

        return True

    @staticmethod
    def _html_alternative(message):
        """Return the text/html alternative body, if the message has one."""
        for content, mimetype in getattr(message, "alternatives", []) or []:
            if mimetype == "text/html":
                return content
        return None

    @staticmethod
    def _reply_to(message):
        """Collect Reply-To addresses from ``reply_to`` or a header override."""
        addresses = [addr for addr in getattr(message, "reply_to", []) or [] if addr]
        if not addresses:
            header = (getattr(message, "extra_headers", None) or {}).get("Reply-To")
            if header:
                addresses = [part.strip() for part in str(header).split(",") if part.strip()]
        return addresses

    @staticmethod
    def _error_detail(response) -> str:
        """Extract Resend's short error message without leaking the payload."""
        try:
            data = response.json()
        except ValueError:
            return "<no JSON body>"
        if isinstance(data, dict):
            detail = data.get("message") or data.get("error")
            if detail:
                return str(detail)[:300]
        return "<unknown error>"

    def _fail(self, message: str, *, status_code: int | None = None) -> bool:
        """Honour ``fail_silently``: log and swallow, or raise to the caller."""
        if self.fail_silently:
            logger.warning("Email delivery failed via Resend: %s", message)
            return False
        raise ResendEmailError(message, status_code=status_code)
