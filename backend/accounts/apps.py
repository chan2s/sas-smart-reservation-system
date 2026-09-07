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


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(self):
        # Register the security check on app initialization.
        from . import apps as _apps  # noqa: F401 — decorator runs at import
