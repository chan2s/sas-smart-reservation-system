"""
Settings override used ONLY by the SQLite→PostgreSQL data-transfer tooling.

Everything else is inherited verbatim from ``config.settings``; the only
change is pointing the ``default`` database alias at the developer's SQLite
file instead of PostgreSQL, so ``dumpdata`` can read the legacy dataset.
No credentials are stored here.
"""

from config.settings import *  # noqa: F401,F403 — deliberate: reuse project settings

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(BASE_DIR / "db.sqlite3"),  # noqa: F405 — from config.settings
    }
}
