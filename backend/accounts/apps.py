from django.apps import AppConfig
from django.core import checks


@checks.register(checks.Tags.security, deploy=True)
def secret_key_length_check(app_configs, **kwargs):
    """Warn when the JWT signing key is below the 32-byte SHA256 minimum.

    SimpleJWT signs with SECRET_KEY (no separate SIGNING_KEY configured), so
    a short key weakens every issued token. Registered as a deploy check: it
    surfaces in `python manage.py check --deploy` and at startup, without
    breaking development with the placeholder dev key.
    """
    from django.conf import settings

    errors = []
    if len(settings.SECRET_KEY.encode("utf-8")) < 32:
        errors.append(
            checks.Warning(
                "DJANGO_SECRET_KEY is shorter than the 32-byte minimum "
                "recommended for SHA256 HMAC signing (SimpleJWT SIGNING_KEY "
                "defaults to it).",
                hint="Set a long random DJANGO_SECRET_KEY in backend/.env "
                "(e.g. python -c \"import secrets; print(secrets.token_urlsafe(64))\").",
                id="sas.W001",
            )
        )
    return errors


@checks.register()
def email_backend_configuration_check(app_configs, **kwargs):
    """Warn when SMTP is selected but the credentials cannot possibly work.

    A missing or placeholder ``EMAIL_HOST_USER`` / ``EMAIL_HOST_PASSWORD`` is
    the usual cause of Gmail's ``535 5.7.8 Username and Password not
    accepted``: the username still triggers an SMTP login attempt that the
    empty or placeholder password can never satisfy. Surfacing that at
    startup is far cheaper than tracing a 535 raised inside an OAuth
    callback.

    Only the *presence* of the values is inspected — never their content —
    so no secret can reach a log or a terminal.
    """
    from django.conf import settings

    backend = getattr(settings, "EMAIL_BACKEND", "")
    if "smtp" not in backend:
        return []  # console / locmem / file backends need no credentials

    placeholders = ("your-", "your_", "change-me", "changeme", "example.com")
    problems = []
    for label in ("EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD"):
        value = getattr(settings, label, "") or ""
        if not value:
            problems.append(f"{label} is not set")
        elif any(token in value.lower() for token in placeholders):
            problems.append(f"{label} still holds the .env.example placeholder")

    if not problems:
        return []
    return [
        checks.Warning(
            f"The SMTP email backend ({backend}) is configured but "
            + "; ".join(problems)
            + ".",
            hint=(
                "Set the real values in backend/.env and then RESTART the "
                "development server: .env is only read when a process "
                "starts, so a running server keeps the old values."
            ),
            id="sas.W002",
        )
    ]


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(self):
        # Register the security check on app initialization.
        from . import apps as _apps  # noqa: F401 — decorator runs at import
