"""
Django settings for the SAS Smart Facility & Resource Reservation System.

Target database architecture is PostgreSQL. The connection is taken from
the ``.env`` file, in priority order:

1. ``DATABASE_URL`` — a complete ``postgres://user:pass@host:port/db`` URL.
2. ``DB_*`` variables — the existing configuration set in ``backend/.env``
   (``DB_CONNECTION``, ``DB_HOST``, ``DB_PORT``, ``DB_DATABASE``,
   ``DB_USERNAME``, ``DB_PASSWORD``).
3. SQLite fallback (``backend/db.sqlite3``) so the app can still run out of
   the box with neither set.

No credentials are ever hardcoded here; everything comes from the
environment loaded by python-dotenv below.
"""

import os
import re
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from backend/.env
ENV_FILE = BASE_DIR / ".env"

# Process environment values take precedence over backend/.env. This is
# required by Docker Compose: its service-level DB_HOST override points the
# backend container at the host PostgreSQL server, while backend/.env keeps
# DB_HOST=127.0.0.1 for commands run directly on Windows. The .env file remains
# the local fallback and is gitignored, so it cannot shadow production config.
#
# NOTE: .env is read ONCE per process. Django's autoreloader watches Python
# files only, so an edited .env still requires a full server restart.
load_dotenv(ENV_FILE, override=False)


def _env_bool(name: str, default: bool = False) -> bool:
    """Read a boolean environment variable ("true", "1", "yes", "on")."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _normalize_from_email(value: str) -> str:
    """Accept both ``Name <address>`` and the common ``Name address>`` typo.

    An email header is a list of addresses, but ``Display Name <address>`` is
    what Django's SMTP backend expects for ``DEFAULT_FROM_EMAIL``. A missing
    opening ``<`` (or missing brackets entirely) otherwise produces an invalid
    From header and Gmail rejects the message. Plain addresses pass through.
    """
    value = (value or "").strip()
    if not value or ("<" in value and ">" in value):
        return value
    match = re.match(r"^(.*?)\s*<?([^<>\s]+@[^<>\s]+)>?$", value)
    if not match:
        return value
    name, address = match.group(1).strip(), match.group(2)
    if not address:
        return value
    return f"{name} <{address}>" if name else address


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]


# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() == "true"

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get(
        "DJANGO_ALLOWED_HOSTS",
        "localhost,127.0.0.1",
    ).split(",")
    if h.strip()
]

# Production reverse-proxy and HTTPS security.
# Caddy terminates public TLS; the backend is not host-published.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECURE_SSL_REDIRECT = _env_bool("DJANGO_SECURE_SSL_REDIRECT", False)
SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_SECURE = _env_bool("CSRF_COOKIE_SECURE", not DEBUG)
SECURE_CONTENT_TYPE_NOSNIFF = True



# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Third-party
    "rest_framework",
    "corsheaders",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",

    # Local apps
    "accounts",
    "facilities",
    "equipment",
    "reservations",
    "notifications",
    "analytics",
    "chatbot",
    "approval_letters",
]


MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


ROOT_URLCONF = "config.urls"


TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


WSGI_APPLICATION = "config.wsgi.application"

# Test runner flushes the cache around every test so DRF throttle counters
# never leak between test cases.
TEST_RUNNER = "config.test_runner.CacheIsolatingRunner"

AUTH_USER_MODEL = "accounts.User"


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def _database_config() -> dict:
    url = os.environ.get("DATABASE_URL")

    if url:
        # Minimal postgres:// URL parser (avoids an extra dependency).
        from urllib.parse import unquote, urlparse

        parsed = urlparse(url)

        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": parsed.path.lstrip("/"),
            "USER": unquote(parsed.username or ""),
            "PASSWORD": unquote(parsed.password or ""),
            "HOST": parsed.hostname or "localhost",
            "PORT": parsed.port or 5432,
        }

    # The existing host/db configuration set in backend/.env. ``DB_CONNECTION``
    # uses driver-style values (pgsql/postgres); anything else keeps SQLite.
    db_connection = (os.environ.get("DB_CONNECTION") or "").strip().lower()

    if db_connection in {"pgsql", "postgres", "postgresql"}:
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("DB_DATABASE", ""),
            "USER": os.environ.get("DB_USERNAME", ""),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", "localhost"),
            "PORT": int(os.environ.get("DB_PORT", "5432")),
        }

    return {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }


DATABASES = {
    "default": _database_config()
}


# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME":
            "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {
        "NAME":
            "django.contrib.auth.password_validation.MinimumLengthValidator"
    },
    {
        "NAME":
            "django.contrib.auth.password_validation.CommonPasswordValidator"
    },
    {
        "NAME":
            "django.contrib.auth.password_validation.NumericPasswordValidator"
    },
]


# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "en-us"

TIME_ZONE = "Asia/Manila"

USE_I18N = True
USE_TZ = True


# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "accounts.jwt.SasJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
        # Global view-only policy: a not-approved (pending) account may read but
        # not change state. Views that override ``permission_classes`` add this
        # explicitly where they can mutate, or omit it where every method is a
        # read-only lookup.
        "accounts.permissions.IsAccountApprovedOrReadOnly",
    ),
    # Global API rate limiting (see accounts/throttling.py for the model).
    # Sensitive endpoints apply stricter endpoint-specific throttles.
    "DEFAULT_THROTTLE_CLASSES": (
        "accounts.throttling.GlobalAnonThrottle",
        "accounts.throttling.GlobalUserThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/min",
        "user": "120/min",
        "auth_login": "5/min",
        "auth_register": "5/min",
        "auth_refresh": "30/min",
        "google_start": "10/min",
        # Chatbot Q&A — modest per-user limit; visitors are IP-limited
        # because the endpoint also serves the public landing/login pages.
        "chatbot": "30/min",
        "chatbot_anon": "10/min",
    },
    "DEFAULT_PAGINATION_CLASS":
        "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": (
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DATETIME_FORMAT": "%Y-%m-%dT%H:%M:%S%z",
    "DATE_FORMAT": "%Y-%m-%d",
    "TIME_FORMAT": "%H:%M",
    # Uniform, internal-free 429 responses.
    "EXCEPTION_HANDLER": "accounts.throttling.throttled_exception_handler",
}


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "UPDATE_LAST_LOGIN": True,
    # A not-approved account keeps its ability to authenticate (and therefore
    # to READ). Approval is enforced per request by
    # accounts.permissions.IsAccountApprovedOrReadOnly, so a token issued
    # before an administrator revoked approval cannot be used to mutate state.
    "CHECK_USER_IS_ACTIVE": False,
    "USER_AUTHENTICATION_RULE": "accounts.jwt.user_authentication_rule",
}


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

AUTHENTICATION_BACKENDS = [
    # Regular username/password authentication. This ModelBackend subclass is
    # identical except that it does not refuse an inactive (not-approved)
    # account — view-only access requires the account to be able to sign in.
    "accounts.backends.AllowInactiveModelBackend",

    # Google OAuth via django-allauth.
    "allauth.account.auth_backends.AuthenticationBackend",
]


SITE_ID = 1

ACCOUNT_EMAIL_VERIFICATION = "none"

ACCOUNT_ADAPTER = "accounts.adapters.AllauthAccountAdapter"

SOCIALACCOUNT_ADAPTER = "accounts.adapters.SasSocialAccountAdapter"


# ---------------------------------------------------------------------------
# Google / django-allauth
# ---------------------------------------------------------------------------

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        # Identity-only scopes.
        "SCOPE": [
            "profile",
            "email",
        ],
        "AUTH_PARAMS": {
            "access_type": "online",
            "prompt": "select_account",
        },
    }
}


# Production hardening.
ACCOUNT_RATE_LIMITS = {
    "login_failed": "5/5m",
}

SOCIALACCOUNT_EMAIL_REQUIRED = True

SOCIALACCOUNT_EMAIL_VERIFICATION = "none"


# ---------------------------------------------------------------------------
# Google OAuth
# ---------------------------------------------------------------------------
# IMPORTANT:
# Credentials must come from backend/.env.
# Never hardcode the client secret here.
# Never expose GOOGLE_CLIENT_SECRET to the React frontend.

GOOGLE_CLIENT_ID = os.environ.get(
    "GOOGLE_CLIENT_ID",
    "",
)

GOOGLE_CLIENT_SECRET = os.environ.get(
    "GOOGLE_CLIENT_SECRET",
    "",
)

# The redirect_uri handed to Google for the authorization code exchange.
#
# Leave EMPTY in development: the backend then derives it from the browser's
# validated frontend origin (config/frontend.py) so localhost, 127.0.0.1, and
# any *.devtunnels.ms all work without code changes — each maps to the same
# path as accounts:google-callback (default /api/auth/google/callback/).
#
# Set it in production (or behind a rewriting proxy) to the exact URL that is
# registered in Google Cloud Console — e.g.
#   GOOGLE_REDIRECT_URI=https://sas.example.com/api/auth/google/callback/
# It must match the registered Authorized redirect URI character-for-character.
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "").strip()


# ---------------------------------------------------------------------------
# Email (Gmail SMTP by default)
# ---------------------------------------------------------------------------
# All credentials come from backend/.env (or the hosting provider's environment
# variables). Nothing here is hardcoded and nothing is exposed to the frontend.
#
# EMAIL_USE_TLS and EMAIL_USE_SSL are mutually exclusive on a real SMTP server:
# port 587 uses TLS, port 465 uses SSL. They are read independently so an
# existing .env keeps working unchanged.

EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend"
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USE_TLS = _env_bool("EMAIL_USE_TLS", True)
EMAIL_USE_SSL = _env_bool("EMAIL_USE_SSL", False)
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = _normalize_from_email(
    os.environ.get("DEFAULT_FROM_EMAIL", "SAS RESERVE <noreply@localhost>")
)
# Keep a hung SMTP connection from blocking the reminder sweep forever.
EMAIL_TIMEOUT = int(os.environ.get("EMAIL_TIMEOUT", "20"))


# ---------------------------------------------------------------------------
# Automatic reservation reminder scheduler
# ---------------------------------------------------------------------------
# The in-process scheduler starts with the backend (see
# reservations.apps.ReservationsConfig.ready) and checks every hour. It is
# disabled automatically for management commands, migrations and tests. Every
# instance competes for a short database lease, so only ONE process actually
# performs a sweep even when several web workers start their own thread.
#
# For a deployment that prefers a separate worker, set
# REMINDER_SCHEDULER_ENABLED=false on the web service and run
# ``python manage.py run_reminder_scheduler`` as a dedicated process.
REMINDER_SCHEDULER_ENABLED = _env_bool("REMINDER_SCHEDULER_ENABLED", True)
REMINDER_SCHEDULER_INTERVAL_SECONDS = int(
    os.environ.get("REMINDER_SCHEDULER_INTERVAL_SECONDS", "3600")
)
# Delay before the first check after a process starts (the check itself runs
# immediately after that; every restart therefore triggers a catch-up sweep).
REMINDER_SCHEDULER_INITIAL_DELAY_SECONDS = int(
    os.environ.get("REMINDER_SCHEDULER_INITIAL_DELAY_SECONDS", "10")
)
# How long a worker may hold the scheduler lease without renewing it. A dead
# worker is replaced within this window; a live worker renews every poll.
REMINDER_SCHEDULER_LEASE_SECONDS = int(
    os.environ.get("REMINDER_SCHEDULER_LEASE_SECONDS", "180")
)
REMINDER_SCHEDULER_POLL_SECONDS = int(
    os.environ.get("REMINDER_SCHEDULER_POLL_SECONDS", "60")
)

# Days before the event the reminder becomes due (three-day reminder window).
RESERVATION_REMINDER_DAYS = int(os.environ.get("RESERVATION_REMINDER_DAYS", "3"))
# A failed/crashed send releases its claim after this long so it can be retried.
REMINDER_EMAIL_CLAIM_TIMEOUT_SECONDS = int(
    os.environ.get("REMINDER_EMAIL_CLAIM_TIMEOUT_SECONDS", "900")
)


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------

PUBLIC_FRONTEND_URL = os.environ.get(
    "PUBLIC_FRONTEND_URL",
    "http://localhost:5173",
)

# Origins allowed to receive OAuth redirects, in addition to localhost in
# DEBUG and (optionally) current VS Code Dev Tunnels. Exact origins only.
FRONTEND_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get("FRONTEND_ALLOWED_ORIGINS", "").split(",")
    if o.strip()
]

# Dev Tunnels: hostname changes on every restart, so trust the domain
# pattern instead of individual hosts. Never enable in production.
ALLOW_DEV_TUNNELS = (
    os.environ.get("ALLOW_DEV_TUNNELS", "true" if DEBUG else "false").lower()
    == "true"
)


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

CORS_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173",
    ).split(",")
    if o.strip()
]

# The frontend normally reaches the API same-origin through the Vite proxy,
# so CORS rarely matters in dev. When a tunnel frontend calls the backend
# cross-origin, its origin must be allowed dynamically without weakening
# production (which pins origins via CORS_ALLOWED_ORIGINS).
if DEBUG and ALLOW_DEV_TUNNELS:
    CORS_ALLOWED_ORIGIN_REGEXES = [
        r"^https://[a-z0-9-]+\.devtunnels\.ms$",
    ]

CORS_ALLOW_CREDENTIALS = True


# ---------------------------------------------------------------------------
# CSRF
# ---------------------------------------------------------------------------

CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
    if o.strip()
]

# Dev Tunnels may expose the backend directly (separate port tunnel). The
# leading-dot entries match any *.devtunnels.ms subdomain and are DEBUG-only:
# production pins hosts explicitly via DJANGO_ALLOWED_HOSTS. The frontend's
# same-origin Vite proxy needs none of this (Host stays 127.0.0.1:8000).
if DEBUG and ALLOW_DEV_TUNNELS:
    ALLOWED_HOSTS.append(".devtunnels.ms")
    CSRF_TRUSTED_ORIGINS.append("https://*.devtunnels.ms")

# ---------------------------------------------------------------------------
# Cache (used by DRF throttling)
# ---------------------------------------------------------------------------
# Development default is per-process local memory, which is fine for a
# single runserver process. In production set CACHE_URL to a shared Redis
# backend (requires `pip install django-redis` or channels_redis's redis)
# so rate limits hold across workers and hosts.

cache_url = os.environ.get("CACHE_URL", "")

if cache_url.startswith("redis://") or cache_url.startswith("rediss://"):
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": cache_url,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }


# ---------------------------------------------------------------------------
# Uploaded images
# ---------------------------------------------------------------------------

DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB
