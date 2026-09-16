"""Seed the chatbot knowledge base with system policies and FAQs.

Only static knowledge lives here — reservation/cancellation policies,
booking instructions, and FAQs. Dynamic data (reservations, availability)
is never seeded: the chatbot queries those tables live.

Run:  python manage.py seed_knowledge_base
"""

from django.core.management.base import BaseCommand

from chatbot.models import KnowledgeBaseEntry

ENTRIES = [
    {
        "category": KnowledgeBaseEntry.Category.RESERVATION_POLICY,
        "title": "Reservation Policy",
        "keywords": "reservation policy booking rules requirements approval process who can book",
        "content": (
            "Anyone with a SAS Reserve account may submit a reservation. All "
            "requests are reviewed by the SAS Office before approval; "
            "reservations created directly by an SAS administrator are "
            "confirmed immediately. Reservations must be submitted in advance "
            "and fall within the facility's operating hours. Equipment is "
            "reserved together with the facility, and availability of both is "
            "checked at submission time."
        ),
    },
    {
        "category": KnowledgeBaseEntry.Category.CANCELLATION_POLICY,
        "title": "Cancellation Policy",
        "keywords": "cancellation policy cancel deadline window refund",
        "content": (
            "Reservations can be cancelled from the reservation detail page. "
            "Requesters cannot cancel a reservation scheduled within the next "
            "2 days (today or tomorrow) — contact the SAS Office for "
            "assistance with those. Completed, rejected, and already-cancelled "
            "reservations cannot be cancelled. Staff and administrators are "
            "not bound by the 2-day window."
        ),
    },
    {
        "category": KnowledgeBaseEntry.Category.BOOKING_GUIDE,
        "title": "How to Make a Reservation",
        "keywords": "how to book reserve make reservation steps instructions create booking",
        "content": (
            "To make a reservation: open the Reservations page and click "
            "\"Create reservation\" (or go to /reservations/new). Choose a "
            "facility, pick a date and time within its operating hours, add "
            "any equipment you need, and submit. You will see a live "
            "availability check before submitting. Once approved you will "
            "receive an email and can check in starting 3 hours before your "
            "event."
        ),
    },
    {
        "category": KnowledgeBaseEntry.Category.BOOKING_GUIDE,
        "title": "Check-in and Check-out",
        "keywords": "check in check out qr code checkin window when can i check in",
        "content": (
            "Check-in opens 3 hours before the event start time. Open your "
            "reservation detail page and use Check in, or let SAS staff scan "
            "your reservation's QR code. When the event ends, SAS staff "
            "perform the check-out, which includes a short facility "
            "inspection."
        ),
    },
    {
        "category": KnowledgeBaseEntry.Category.FAQ,
        "title": "Who can use the system?",
        "keywords": "who can use account access requester staff admin external",
        "content": (
            "SAS Reserve is for campus users (students and employees with "
            "accounts) and external organizations. External requesters do not "
            "need an account — SAS staff can create reservations on their "
            "behalf. Administrators and SAS staff manage approvals, "
            "facilities, and equipment."
        ),
    },
    {
        "category": KnowledgeBaseEntry.Category.FAQ,
        "title": "What happens after I submit a reservation?",
        "keywords": "after submit pending approval notification email status what happens",
        "content": (
            "New reservations enter the Pending queue and the SAS Office is "
            "notified immediately. You will receive an email and an in-app "
            "notification when your reservation is approved or rejected. You "
            "can track the status any time on the Reservations page or by "
            "asking me about your reservations."
        ),
    },
    {
        "category": KnowledgeBaseEntry.Category.GENERAL,
        "title": "About SAS Reserve",
        "keywords": "about system what is sas reserve purpose",
        "content": (
            "SAS Reserve is the campus facility and resource reservation "
            "system operated by the Student Affairs Services (SAS) Office. "
            "It manages facility bookings, equipment loans, approvals, "
            "check-ins, and maintenance tracking."
        ),
    },
]


class Command(BaseCommand):
    help = "Seed the chatbot knowledge base with policies and FAQs."

    def handle(self, *args, **options):
        created = 0
        for data in ENTRIES:
            _, was_created = KnowledgeBaseEntry.objects.get_or_create(
                title=data["title"],
                defaults={
                    "category": data["category"],
                    "content": data["content"],
                    "keywords": data["keywords"],
                    "status": KnowledgeBaseEntry.Status.PUBLISHED,
                },
            )
            if was_created:
                created += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Knowledge base seeded ({created} new, "
                f"{len(ENTRIES) - created} existing)."
            )
        )
