"""Chatbot tests.

Covers the requirements that matter for a non-AI, database-grounded bot:
deterministic intent detection, live-data freshness, role scoping, template
grounding (no invented values), and fallback behavior.
"""

from datetime import date, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from chatbot.services.entities import extract_entities
from chatbot.services.intents import Intent, detect_intent
from chatbot.services.pipeline import process_message

from facilities.models import Facility, OperatingHour
from reservations.models import Reservation

User = get_user_model()


class IntentDetectionTests(TestCase):
    def test_check_availability(self):
        self.assertEqual(detect_intent("Is the AVR available tomorrow at 2 PM?").intent, Intent.CHECK_AVAILABILITY)

    def test_cancellation_policy_beats_cancel_action(self):
        self.assertEqual(detect_intent("What is the cancellation policy?").intent, Intent.CANCELLATION_POLICY)

    def test_cancel_action(self):
        self.assertEqual(detect_intent("I want to cancel my reservation").intent, Intent.CANCEL_RESERVATION)

    def test_view_reservation(self):
        self.assertEqual(detect_intent("Where is my reservation SAS-2026-00012?").intent, Intent.VIEW_RESERVATION)

    def test_out_of_scope(self):
        self.assertEqual(detect_intent("What is the capital of France?").intent, Intent.UNKNOWN)

    def test_help(self):
        self.assertEqual(detect_intent("help").intent, Intent.SYSTEM_HELP)


class EntityExtractionTests(TestCase):
    def test_relative_date(self):
        entities = extract_entities("Is the AVR available tomorrow at 2 PM?")
        self.assertEqual(entities.date, date.today() + timedelta(days=1))
        self.assertEqual(entities.start_time, time(14, 0))

    def test_month_day_date(self):
        entities = extract_entities("Is the gym free on September 20?")
        # Year rolls over if the date already passed this year.
        today = date.today()
        expected = date(today.year, 9, 20)
        if expected < today:
            expected = date(today.year + 1, 9, 20)
        self.assertEqual(entities.date, expected)

    def test_reservation_id(self):
        entities = extract_entities("Where is my reservation SAS-2026-00012?")
        self.assertEqual(entities.reservation_id, "SAS-2026-00012")

    def test_24h_time(self):
        entities = extract_entities("Is the AVR available 2026-09-20 at 14:00?")
        self.assertEqual(entities.start_time, time(14, 0))


class AvailabilityPipelineTests(TestCase):
    """End-to-end pipeline behavior against a controlled database."""

    @classmethod
    def setUpTestData(cls):
        cls.facility = Facility.objects.create(
            name="Test Hall",
            facility_type=Facility.FacilityType.OTHER,
            capacity=50,
            location="Test Building",
            description="A test facility.",
            rules=["No food", "Be quiet"],
        )
        for day in range(7):
            OperatingHour.objects.create(
                facility=cls.facility,
                day_of_week=day,
                open_time=time(8, 0),
                close_time=time(18, 0),
            )
        cls.requester = User.objects.create_user(
            username="chatreq",
            email="chatreq@example.com",
            password="testpass1234",
            first_name="Chat",
            last_name="Requester",
        )
        cls.staff = User.objects.create_user(
            username="chatstaff",
            email="chatstaff@example.com",
            password="testpass1234",
            first_name="Chat",
            last_name="Staff",
            role=User.Role.STAFF,
        )

    def _reserve(self, **kwargs):
        defaults = dict(
            requester=self.requester,
            event_name="Test Event",
            facility=self.facility,
            date=date.today() + timedelta(days=5),
            start_time=time(10, 0),
            end_time=time(12, 0),
            status=Reservation.Status.APPROVED,
        )
        defaults.update(kwargs)
        return Reservation.objects.create(**defaults)

    def test_available_answer(self):
        target = date.today() + timedelta(days=5)
        result = process_message(self.requester, f"Is {self.facility.name} available on {target.isoformat()} at 9 AM?")
        self.assertIn("available", result["message"].lower())
        self.assertEqual(result["intent"], Intent.CHECK_AVAILABILITY)
        self.assertEqual(result["source"], "database")

    def test_conflicting_reservation_answer(self):
        target = date.today() + timedelta(days=5)
        self._reserve()  # 10:00-12:00 approved
        result = process_message(self.requester, f"Is {self.facility.name} available on {target.isoformat()} at 11 AM?")
        self.assertIn("unavailable", result["message"].lower())
        self.assertIn("existing reservation", result["message"].lower())
        self.assertEqual(result["source"], "database")

    def test_freshness_after_cancellation(self):
        """The same question must flip answers when the DB changes."""
        target = date.today() + timedelta(days=5)
        reservation = self._reserve()
        before = process_message(self.requester, f"Is {self.facility.name} available on {target.isoformat()} at 11 AM?")
        self.assertIn("unavailable", before["message"].lower())

        reservation.status = Reservation.Status.CANCELLED
        reservation.save()
        after = process_message(self.requester, f"Is {self.facility.name} available on {target.isoformat()} at 11 AM?")
        self.assertIn("available", after["message"].lower())
        self.assertNotIn("unavailable", after["message"].lower())

    def test_whole_day_free_windows(self):
        target = date.today() + timedelta(days=5)
        self._reserve(start_time=time(10, 0), end_time=time(12, 0))
        result = process_message(self.requester, f"Is {self.facility.name} available on {target.isoformat()}?")
        self.assertIn("free windows", result["message"].lower())

    def test_maintenance_answer(self):
        target = date.today() + timedelta(days=5)
        self.facility.status = Facility.Status.MAINTENANCE
        self.facility.save()
        try:
            result = process_message(self.requester, f"Is {self.facility.name} available on {target.isoformat()} at 9 AM?")
            self.assertIn("maintenance", result["message"].lower())
        finally:
            self.facility.status = Facility.Status.OPERATIONAL
            self.facility.save()

    def test_unknown_facility(self):
        result = process_message(self.requester, "Is the Reactor Bay available tomorrow at 2 PM?")
        self.assertIn("couldn't find a facility", result["message"].lower())

    def test_missing_date_prompt(self):
        result = process_message(self.requester, f"Is {self.facility.name} available?")
        self.assertIn("which date", result["message"].lower())


class ReservationLookupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.facility = Facility.objects.create(
            name="Lookup Hall",
            facility_type=Facility.FacilityType.OTHER,
            capacity=10,
        )
        for day in range(7):
            OperatingHour.objects.create(
                facility=cls.facility, day_of_week=day,
                open_time=time(8, 0), close_time=time(18, 0),
            )
        cls.owner = User.objects.create_user(
            username="owner1", email="owner1@example.com", password="testpass1234",
        )
        cls.other = User.objects.create_user(
            username="other1", email="other1@example.com", password="testpass1234",
        )
        cls.staff = User.objects.create_user(
            username="lookupstaff", email="lookupstaff@example.com",
            password="testpass1234", role=User.Role.STAFF,
        )
        cls.reservation = Reservation.objects.create(
            requester=cls.owner,
            event_name="Private Event",
            facility=cls.facility,
            date=date.today() + timedelta(days=3),
            start_time=time(9, 0),
            end_time=time(10, 0),
            status=Reservation.Status.APPROVED,
        )

    def test_owner_sees_own_reservation(self):
        result = process_message(self.owner, f"Where is my reservation {self.reservation.reservation_id}?")
        self.assertIn("Private Event", result["message"])
        self.assertEqual(result["source"], "database")

    def test_other_user_cannot_see_it(self):
        result = process_message(self.other, f"Where is my reservation {self.reservation.reservation_id}?")
        self.assertNotIn("Private Event", result["message"])

    def test_staff_sees_all(self):
        result = process_message(self.staff, f"Where is my reservation {self.reservation.reservation_id}?")
        self.assertIn("Private Event", result["message"])

    def test_my_reservations_lists_only_own(self):
        result = process_message(self.other, "Show my reservations")
        self.assertNotIn("Private Event", result["message"])


class KnowledgeBaseTests(TestCase):
    def test_policy_answer_from_kb(self):
        from chatbot.models import KnowledgeBaseEntry

        KnowledgeBaseEntry.objects.create(
            category=KnowledgeBaseEntry.Category.CANCELLATION_POLICY,
            title="Cancellation Policy",
            content="Cancellations require 3 days notice.",
            keywords="cancellation policy cancel",
            status=KnowledgeBaseEntry.Status.PUBLISHED,
        )
        requester = User.objects.create_user(
            username="kbuser", email="kbuser@example.com", password="testpass1234",
        )
        result = process_message(requester, "What is the cancellation policy?")
        self.assertIn("3 days notice", result["message"])
        self.assertEqual(result["source"], "knowledge")

    def test_draft_entries_never_served(self):
        from chatbot.models import KnowledgeBaseEntry

        KnowledgeBaseEntry.objects.create(
            category=KnowledgeBaseEntry.Category.FAQ,
            title="Secret Draft",
            content="This is a draft policy.",
            keywords="draft policy",
            status=KnowledgeBaseEntry.Status.DRAFT,
        )
        requester = User.objects.create_user(
            username="draftuser", email="draftuser@example.com", password="testpass1234",
        )
        result = process_message(requester, "What is the draft policy?")
        self.assertNotIn("draft policy", result["message"].lower())


class ChatEndpointTests(TestCase):
    """HTTP-level auth, permissions, and response shape."""

    @classmethod
    def setUpTestData(cls):
        cls.client_class = APIClient
        cls.user = User.objects.create_user(
            username="apiuser", email="apiuser@example.com", password="testpass1234",
        )

    def setUp(self):
        self.api = APIClient()
        self.api.force_authenticate(user=self.user)

    def test_requires_authentication(self):
        anon = APIClient()
        response = anon.post("/api/chatbot/", {"message": "hello"}, format="json")
        self.assertEqual(response.status_code, 401)

    def test_response_shape(self):
        response = self.api.post("/api/chatbot/", {"message": "help"}, format="json")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        for key in ("message", "intent", "source"):
            self.assertIn(key, body)

    def test_empty_message_rejected(self):
        response = self.api.post("/api/chatbot/", {"message": ""}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_chat_log_written(self):
        from chatbot.models import ChatLog

        before = ChatLog.objects.count()
        self.api.post("/api/chatbot/", {"message": "help"}, format="json")
        self.assertEqual(ChatLog.objects.count(), before + 1)
