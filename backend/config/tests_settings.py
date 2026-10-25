"""Settings behavior needed by the Windows and Docker development stack."""

import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase


class EnvironmentPrecedenceTests(SimpleTestCase):
    def test_process_database_host_overrides_backend_dotenv(self):
        env = os.environ.copy()
        env.update(
            {
                "DJANGO_SETTINGS_MODULE": "config.settings",
                "DJANGO_SECRET_KEY": "settings-test-only",
                "DATABASE_URL": "",
                "DB_CONNECTION": "pgsql",
                "DB_DATABASE": "settings_test",
                "DB_USERNAME": "settings_test",
                "DB_PASSWORD": "settings_test",
                "DB_HOST": "compose-db-host",
                "DB_PORT": "5432",
            }
        )
        settings_probe = (
            "from django.conf import settings; "
            "print(settings.DATABASES['default']['HOST'])"
        )
        result = subprocess.run(
            [sys.executable, "-c", settings_probe],
            cwd=Path(__file__).resolve().parent.parent,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.stdout.strip(), "compose-db-host")
