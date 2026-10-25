"""Create missing letters and retry pending DOCX generation for approvals."""

from django.core.management.base import BaseCommand

from approval_letters.services import create_letter_for_reservation
from reservations.models import Reservation


class Command(BaseCommand):
    help = "Reconcile approval letters for approved reservations."

    def handle(self, *args, **options):
        reservations = Reservation.objects.filter(
            status__in=(
                Reservation.Status.APPROVED,
                Reservation.Status.ACTIVE,
                Reservation.Status.COMPLETED,
                Reservation.Status.NO_SHOW,
            )
        ).select_related("requester", "facility", "created_by")

        processed = 0
        failures = 0
        for reservation in reservations.iterator():
            try:
                create_letter_for_reservation(reservation)
                processed += 1
            except Exception:  # keep reconciling other approvals
                failures += 1
                self.stderr.write(
                    f"Could not reconcile letter for reservation "
                    f"{reservation.reservation_id}. Check server logs."
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Reconciled {processed} approved reservations; {failures} failed."
            )
        )
