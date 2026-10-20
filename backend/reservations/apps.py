import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class ReservationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "reservations"

    def ready(self):
        """Start the automatic reminder checker with the backend process.

        ``reservations.scheduler`` decides whether this process is appropriate
        (it skips migrations, tests, other management commands, and the
        runserver autoreloader parent). Starting is best-effort: a scheduler
        problem must never prevent the API from booting.
        """
        try:
            from reservations import scheduler

            scheduler.start_scheduler()
        except Exception:  # noqa: BLE001 — never block backend startup
            logger.exception("Could not start the automatic reminder scheduler.")
