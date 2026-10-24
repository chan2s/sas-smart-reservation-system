"""Cron-compatible possible-no-show alert sweep.

Creates/updates the administrator warnings for APPROVED reservations that are
inside the 15-minute warning window or past their start time without a recorded
check-in, and resolves alerts whose reservation is no longer eligible.

It never changes a reservation's status and never sends email, so it is safe to
run every five minutes. Running it repeatedly creates no duplicates: each
reservation owns exactly one alert row, which is updated in place.

Examples
--------

Development / manual check::

    python manage.py process_reservation_notifications

Windows Task Scheduler (every 5 minutes), "Program/script"::

    C:\\Python313\\python.exe

"Add arguments"::

    manage.py process_reservation_notifications --quiet

"Start in"::

    C:\\Users\\Cristian\\SAS Smart Facility and Resource Reservation System\\backend

Linux crontab::

    */5 * * * * cd /path/to/backend && /path/to/python manage.py process_reservation_notifications --quiet
"""

from django.core.management.base import BaseCommand

from notifications import no_show_alerts


class Command(BaseCommand):
    help = (
        "Create/update/resolve administrator possible-no-show alerts for "
        "approved reservations that are starting or have started without a "
        "check-in. Safe to run every five minutes."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Only print output when something changed (for Task Scheduler).",
        )

    def handle(self, *args, **options):
        summary = no_show_alerts.refresh_alerts()
        changed = summary["created"] or summary["updated"] or summary["resolved"]
        if options["quiet"] and not changed:
            return
        self.stdout.write(
            self.style.SUCCESS(
                "Possible no-show alerts: {active} active, {created} created, "
                "{updated} updated, {escalated} escalated, {resolved} "
                "resolved.".format(**summary)
            )
        )
