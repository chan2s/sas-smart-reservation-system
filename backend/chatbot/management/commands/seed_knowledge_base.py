"""Seed the chatbot knowledge base with system policies and FAQs.

Only static knowledge lives here — reservation/cancellation policies,
booking instructions, registration/login help, and FAQs. Dynamic data
(reservations, availability) is never seeded: the chatbot queries those
tables live.

Each entry carries a visibility class: PUBLIC entries are also served to
unauthenticated visitors on the landing/login/register pages;
AUTHENTICATED entries require a signed-in user.

Run:  python manage.py seed_knowledge_base
"""

from django.core.management.base import BaseCommand

from chatbot.models import KnowledgeBaseEntry

V = KnowledgeBaseEntry.Visibility

ENTRIES = [
    {
        "category": KnowledgeBaseEntry.Category.RESERVATION_POLICY,
        "title": "Reservation Policy",
        "keywords": "reservation policy booking rules requirements approval process who can book",
        "visibility": V.PUBLIC,
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
        "visibility": V.PUBLIC,
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
        "visibility": V.PUBLIC,
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
        "visibility": V.AUTHENTICATED,
        "content": (
            "Check-in opens 3 hours before the event start time. Open your "
            "reservation detail page and use Check in, or let SAS staff scan "
            "your reservation's QR code. When the event ends, SAS staff "
            "perform the check-out, which includes a short facility "
            "inspection."
        ),
    },
    {
        "category": KnowledgeBaseEntry.Category.REGISTRATION_HELP,
        "title": "How to Register",
        "keywords": "how do i register sign up create account registration activate what information need",
        "visibility": V.PUBLIC,
        "content": (
            "To register: click Register on the home page (or go to "
            "/register) and fill in your first name, last name, email, "
            "username, and password. Campus users register with their school "
            "email; external organizations may add their organization name. "
            "Once registered, log in with your username and password to "
            "submit reservations. External guests do not need an account — "
            "SAS staff can create reservations on their behalf."
        ),
    },
    {
        "category": KnowledgeBaseEntry.Category.LOGIN_HELP,
        "title": "How to Log In",
        "keywords": "how do i log in sign in forgot password reset username cannot log in access reservation system",
        "visibility": V.PUBLIC,
        "content": (
            "To log in: click Login on the home page (or go to /login) and "
            "enter your username and password. You can also sign in with "
            "Google using your school account. If you forgot your password, "
            "contact the SAS Office to have it reset — the system does not "
            "offer self-service password resets. New accounts can log in "
            "immediately after registering."
        ),
    },
    {
        "category": KnowledgeBaseEntry.Category.ANNOUNCEMENT,
        "title": "Welcome to SAS Reserve",
        "keywords": "announcement news welcome advisory new",
        "visibility": V.PUBLIC,
        "content": (
            "SAS Reserve is now open to campus organizations and external "
            "guests. Browse facilities, check availability, and submit "
            "reservation requests online — the SAS Office reviews every "
            "request and notifies you by email."
        ),
    },
    {
        "category": KnowledgeBaseEntry.Category.FAQ,
        "title": "Who can use the system?",
        "keywords": "who can use account access requester staff admin external",
        "visibility": V.PUBLIC,
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
        "visibility": V.AUTHENTICATED,
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
        "visibility": V.PUBLIC,
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
                    "visibility": data["visibility"],
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
