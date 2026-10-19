"""Cron-compatible upcoming-reservation reminder sweep.

Sends the existing in-app reminder to requesters whose APPROVED reservation is
three calendar days away (or sooner, when it was approved inside that window).
Idempotent and concurrency-safe: each reservation is reminded at most once, so
the command can be scheduled hourly and safely retried.

Example crontab entry (Asia/Manila server time):

    0 * * * * cd /path/to/backend && /path/to/python manage.py send_reservation_reminders >> /var/log/sas-reserve-reminders.log 2>&1
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from reservations.models import Reservation
from reservations.services import reminders


class Command(BaseCommand):
    help = (
        "Send the automatic three-days-before reminder for APPROVED "
        "reservations through the in-app notification system. Safe to run "
        "repeatedly; each reservation is reminded at most once."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many reminders are due without sending them.",
        )

    def handle(self, *args, **options):
        if options["dry_run"]:
            due = [
                reservation
                for reservation in Reservation.objects.select_related(
                    "facility", "requester"
                ).filter(
                    status=Reservation.Status.APPROVED,
                    reminder_sent_at__isnull=True,
                )
                if reminders.is_reminder_due(reservation, timezone.now())
            ]
            self.stdout.write(
                self.style.SUCCESS(f"{len(due)} reminder(s) are due (dry run).")
            )
            return

        result = reminders.send_due_reminders()
        self.stdout.write(
            self.style.SUCCESS(
                "Reminders processed: {sent} sent, {skipped} skipped, "
                "{failed} failed (out of {scanned} scanned).".format(**result)
            )
        )
