"""Cron-compatible expiration sweep.

Runs the same idempotent expiration the API enforces on every reservation read,
so it can be scheduled (e.g. a Render cron job) without any paid background
worker. Safe to run as often as desired.
"""

from django.core.management.base import BaseCommand

from reservations.services import expiration


class Command(BaseCommand):
    help = (
        "Move PENDING reservations whose scheduled event start time has already "
        "passed to the EXPIRED status. Never deletes anything."
    )

    def handle(self, *args, **options):
        count = expiration.expire_overdue_reservations()
        self.stdout.write(
            self.style.SUCCESS(f"Expired {count} overdue reservation(s).")
        )
