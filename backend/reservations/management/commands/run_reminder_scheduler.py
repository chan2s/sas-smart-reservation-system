"""Long-running automatic reservation reminder scheduler.

Use this as a dedicated worker when the web processes must not run background
threads:

    REMINDER_SCHEDULER_ENABLED=false   # on the web service
    python manage.py run_reminder_scheduler

It performs an immediate catch-up sweep on startup and then checks hourly. The
same database lease used by the in-process scheduler prevents overlap, and the
per-reservation email claim makes every run idempotent.
"""

import os
import uuid

from django.core.management.base import BaseCommand

from reservations import scheduler


class Command(BaseCommand):
    help = (
        "Run the automatic upcoming-reservation reminder scheduler in the "
        "foreground. Checks immediately, then every hour (or --interval)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval",
            type=int,
            default=None,
            metavar="SECONDS",
            help="Seconds between checks (default: REMINDER_SCHEDULER_INTERVAL_SECONDS).",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="Run a single reminder sweep and exit.",
        )

    def handle(self, *args, **options):
        if options["once"]:
            summary = scheduler.run_sweep_once()
            self.stdout.write(
                self.style.SUCCESS(
                    "Reminders processed: {sent} delivered, {skipped} skipped, "
                    "{failed} failed; {emails_sent} email(s) sent.".format(**summary)
                )
            )
            return

        owner = f"cli-{os.getpid()}-{uuid.uuid4().hex[:12]}"
        self.stdout.write(
            self.style.SUCCESS(
                "Starting reminder scheduler (Ctrl+C to stop). The first check "
                "runs immediately."
            )
        )
        try:
            scheduler.run_loop(
                owner,
                interval_seconds=options["interval"],
                initial_delay_seconds=0,
            )
        except KeyboardInterrupt:
            self.stdout.write("Reminder scheduler stopped.")
        finally:
            scheduler.release_lease(owner)
