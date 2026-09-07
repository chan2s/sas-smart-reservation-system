"""
Django settings for the SAS Smart Facility & Resource Reservation System.

Target database architecture is PostgreSQL. During local development the
database can be selected through the ``DATABASE_URL`` environment variable
(e.g. ``postgres://user:pass@localhost:5432/sas_reserve``). When it is not
set, the project falls back to SQLite so the app can be run out of the box.
"""

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from backend/.env
load_dotenv(BASE_DIR / ".env")


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-qp0_ea4xb!gh+6owa*^=051(!l*dc-noin5(g+6gty7rpi(vho",
)


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
    "django_otp",
    "django_otp.plugins.otp_totp",

    # Local apps
    "accounts",
    "facilities",
    "equipment",
    "reservations",
    "notifications",
    "analytics",
]


MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
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

MEDIA_URL = "media/"
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
        # DRF periods are single-char: s/m/h/d — 10 min = 600 s.
        "otp_verify": "5/600s",
        "otp_resend": "3/600s",
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
}


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

AUTHENTICATION_BACKENDS = [
    # Regular username/password authentication.
    "django.contrib.auth.backends.ModelBackend",

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
# django-otp
# ---------------------------------------------------------------------------

OTP_TOTP_ISSUER = "SAS RESERVE"


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


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------

PUBLIC_FRONTEND_URL = os.environ.get(
    "PUBLIC_FRONTEND_URL",
    "http://localhost:5173",
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

CORS_ALLOW_CREDENTIALS = True


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
# Credentials come from backend/.env — never hardcoded, never committed.
# Tests use django.core.mail.backends.locmem.EmailBackend automatically via
# Django's test runner, so no real SMTP is touched in CI/tests.

EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "true").lower() == "true"
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL",
    "SAS RESERVE <no-reply@example.com>",
)


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