"""Tests for the frontend links embedded in reservation emails.

Every reservation email links back to the SPA. That link must be built from
``PUBLIC_FRONTEND_URL`` — the deployed origin in production, the Vite origin in
local development — never from a hard-coded or default ``localhost:5173``.
"""

from datetime import date, time

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings

from facilities.models import Facility
from notifications import email_service
from reservations.models import Reservation

User = get_user_model()

PUBLIC_URL = "https://reserve.norsu.edu.ph"
LOCAL_URL = "http://localhost:5173"


class EmailLinkTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.requester = User.objects.create_user(
            username="link-requester",
            password="pass12345",
            role=User.Role.REQUESTER,
            first_name="Maria",
            last_name="Santos",
            email="maria@campus.edu",
        )
        cls.facility = Facility.objects.create(
            name="Link Test AVR",
            facility_type=Facility.FacilityType.AVR,
            capacity=60,
        )

    def make_reservation(self, **overrides):
        defaults = dict(
            requester=self.requester,
            requester_type=Reservation.RequesterType.CAMPUS,
            contact_email=self.requester.email,
            event_name="Student Leadership Summit",
            event_type=Reservation.EventType.SEMINAR,
            facility=self.facility,
            date=date(2026, 11, 2),
            start_time=time(9, 0),
            end_time=time(11, 0),
            status=Reservation.Status.PENDING,
        )
        defaults.update(overrides)
        return Reservation.objects.create(**defaults)

    def senders(self, reservation):
        """Every reservation email that carries the "View your reservation" link.

        The no-show plain-text template has never included the link (only its
        HTML alternative does), so ``text_link`` records which parts of the
        message are expected to carry it. This test changes no wording.
        """
        return [
            (
                "approval",
                True,
                lambda: email_service.send_reservation_approved(reservation, None),
            ),
            (
                "confirmation",
                True,
                lambda: email_service.send_booking_confirmation(reservation),
            ),
            (
                "check-in reminder",
                True,
                lambda: email_service.send_reservation_checkin_reminder(reservation),
            ),
            (
                "reminder",
                True,
                lambda: email_service.send_reservation_reminder(reservation),
            ),
            (
                "no-show",
                False,
                lambda: email_service.send_reservation_no_show_notice(
                    reservation, None
                ),
            ),
        ]

    # ------------------------------------------------------------------
    # Production: the configured public origin, on the correct route
    # ------------------------------------------------------------------

    @override_settings(PUBLIC_FRONTEND_URL=f"{PUBLIC_URL}/", IS_PRODUCTION=True)
    def test_production_reservation_email_uses_the_public_frontend_url(self):
        reservation = self.make_reservation()

        ok, reason = email_service.send_reservation_approved(reservation, None)
        self.assertTrue(ok, reason)
        self.assertEqual(len(mail.outbox), 1)

        sent = mail.outbox[0]
        expected = f"{PUBLIC_URL}/reservations/{reservation.pk}"
        self.assertIn(expected, sent.body)
        self.assertIn(expected, sent.alternatives[0][0])
        # The trailing slash on the configured base must not double up.
        self.assertNotIn(f"{PUBLIC_URL}//reservations", sent.body)

    @override_settings(PUBLIC_FRONTEND_URL=PUBLIC_URL, IS_PRODUCTION=True)
    def test_production_email_never_contains_a_localhost_link(self):
        reservation = self.make_reservation()

        ok, reason = email_service.send_reservation_approved(reservation, None)
        self.assertTrue(ok, reason)

        sent = mail.outbox[0]
        for payload in (sent.body, sent.alternatives[0][0]):
            self.assertNotIn("localhost:5173", payload)
            self.assertNotIn("localhost", payload)
            self.assertNotIn("127.0.0.1", payload)

    @override_settings(PUBLIC_FRONTEND_URL=PUBLIC_URL, IS_PRODUCTION=True)
    def test_every_reservation_email_links_to_the_public_frontend(self):
        reservation = self.make_reservation()
        expected = f"{PUBLIC_URL}/reservations/{reservation.pk}"

        for label, text_link, send in self.senders(reservation):
            with self.subTest(email=label):
                mail.outbox.clear()
                ok, reason = send()
                self.assertTrue(ok, reason)
                self.assertEqual(len(mail.outbox), 1)
                sent = mail.outbox[0]
                html = sent.alternatives[0][0]
                self.assertIn(expected, html)
                for payload in (sent.body, html):
                    self.assertNotIn("localhost", payload)
                    self.assertNotIn("127.0.0.1", payload)
                if text_link:
                    self.assertIn(expected, sent.body)

    # ------------------------------------------------------------------
    # Local development: the configured local origin still works
    # ------------------------------------------------------------------

    @override_settings(PUBLIC_FRONTEND_URL=LOCAL_URL, IS_PRODUCTION=False)
    def test_local_development_uses_the_configured_local_url(self):
        reservation = self.make_reservation()

        ok, reason = email_service.send_reservation_approved(reservation, None)
        self.assertTrue(ok, reason)

        sent = mail.outbox[0]
        expected = f"{LOCAL_URL}/reservations/{reservation.pk}"
        self.assertIn(expected, sent.body)
        self.assertIn(expected, sent.alternatives[0][0])

    # ------------------------------------------------------------------
    # Misconfiguration: fail safely, log clearly, send nothing bogus
    # ------------------------------------------------------------------

    @override_settings(PUBLIC_FRONTEND_URL="", IS_PRODUCTION=True)
    def test_missing_public_url_sends_nothing_and_logs_a_configuration_error(self):
        reservation = self.make_reservation()

        with self.assertLogs("notifications.email_service", level="ERROR") as logs:
            ok, reason = email_service.send_reservation_approved(reservation, None)

        self.assertFalse(ok)
        self.assertEqual(reason, "configuration")
        self.assertEqual(len(mail.outbox), 0)
        self.assertIn("PUBLIC_FRONTEND_URL", "\n".join(logs.output))

    @override_settings(PUBLIC_FRONTEND_URL=f"  {LOCAL_URL}/  ", IS_PRODUCTION=True)
    def test_localhost_public_url_is_rejected_in_production(self):
        reservation = self.make_reservation()

        with self.assertLogs("notifications.email_service", level="ERROR") as logs:
            ok, reason = email_service.send_reservation_approved(reservation, None)

        self.assertFalse(ok)
        self.assertEqual(reason, "configuration")
        self.assertEqual(len(mail.outbox), 0)
        self.assertIn("local development host", "\n".join(logs.output))

    @override_settings(PUBLIC_FRONTEND_URL="not-a-url", IS_PRODUCTION=True)
    def test_invalid_public_url_is_rejected(self):
        reservation = self.make_reservation()

        with self.assertLogs("notifications.email_service", level="ERROR"):
            ok, reason = email_service.send_reservation_approved(reservation, None)

        self.assertFalse(ok)
        self.assertEqual(reason, "configuration")
        self.assertEqual(len(mail.outbox), 0)

    # ------------------------------------------------------------------
    # URL construction helpers
    # ------------------------------------------------------------------

    @override_settings(PUBLIC_FRONTEND_URL=f" {PUBLIC_URL}/ ", IS_PRODUCTION=True)
    def test_frontend_url_is_normalized(self):
        self.assertEqual(
            email_service.build_frontend_url("/reservations/1"),
            f"{PUBLIC_URL}/reservations/1",
        )
        self.assertEqual(
            email_service.build_frontend_url("reservations/1"),
            f"{PUBLIC_URL}/reservations/1",
        )

    @override_settings(PUBLIC_FRONTEND_URL=PUBLIC_URL, IS_PRODUCTION=True)
    def test_reservation_url_uses_the_detail_route_and_primary_key(self):
        reservation = self.make_reservation()

        self.assertEqual(
            email_service.build_reservation_url(reservation),
            f"{PUBLIC_URL}/reservations/{reservation.pk}",
        )
