"""Tests for the automatic booking confirmation email.

The confirmation is triggered by a SUCCESSFUL reservation creation on the
Django backend and dispatched with ``transaction.on_commit`` after the
reservation is committed. Django's test runner replaces the configured SMTP
backend with the locmem backend, so these tests inspect ``mail.outbox`` and
never send a real email.
"""

import smtplib
from datetime import time, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.template.defaultfilters import date as format_date
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from equipment.models import Equipment, EquipmentCategory
from facilities.models import Facility, OperatingHour
from reservations.models import Reservation
from reservations.services import confirmations

User = get_user_model()

SUBJECT = "SAS RESERVE - Booking Confirmation"


class BookingConfirmationEmailTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.requester = User.objects.create_user(
            username="requester",
            password="pass12345",
            role=User.Role.REQUESTER,
            first_name="Maria",
            last_name="Santos",
            email="maria@campus.edu",
        )
        self.admin = User.objects.create_user(
            username="admin",
            password="pass12345",
            role=User.Role.ADMIN,
            first_name="Alex",
            last_name="Reyes",
            email="admin@campus.edu",
        )
        self.facility = Facility.objects.create(
            name="SAS AVR",
            facility_type=Facility.FacilityType.AVR,
            capacity=100,
        )
        OperatingHour.objects.create(
            facility=self.facility,
            day_of_week=0,
            open_time=time(6, 0),
            close_time=time(22, 0),
        )
        category = EquipmentCategory.objects.create(name="Seating")
        self.chairs = Equipment.objects.create(
            name="Monobloc Chair",
            category=category,
            total_quantity=100,
        )
        # A near-future Monday so the Monday-only operating hours line up.
        self.day = timezone.localdate() + timedelta(days=1)
        while self.day.weekday() != 0:
            self.day += timedelta(days=1)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _payload(self, **overrides):
        payload = dict(
            facility_id=self.facility.id,
            date=self.day.isoformat(),
            start_time="09:00",
            end_time="11:00",
            event_name="Student Leadership Summit",
            event_type="SEMINAR",
            organization="Student Affairs",
            purpose="Leadership training",
            expected_participants=80,
            items=[{"equipment_id": self.chairs.id, "quantity": 80}],
        )
        payload.update(overrides)
        return payload

    def _create(self, payload=None):
        """POST a reservation and run the post-commit email callback."""
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(
                "/api/reservations/", payload or self._payload(), format="json"
            )

    # ------------------------------------------------------------------
    # 1-3: a successful creation sends one correct email to the requester
    # ------------------------------------------------------------------

    def test_successful_creation_sends_confirmation_to_requester(self):
        self.client.force_authenticate(self.requester)
        response = self._create()

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.subject, SUBJECT)
        self.assertEqual(sent.to, [self.requester.email])

        reservation = Reservation.objects.get(pk=response.json()["id"])
        self.assertEqual(reservation.status, Reservation.Status.PENDING)
        self.assertIsNotNone(reservation.confirmation_email_sent_at)

    def test_email_contains_the_reservation_details(self):
        self.client.force_authenticate(self.requester)
        response = self._create()
        reservation = Reservation.objects.get(pk=response.json()["id"])
        body = mail.outbox[0].body

        self.assertIn("NORSU-BSC", body)
        self.assertIn("Maria Santos", body)
        self.assertIn(reservation.reservation_id, body)
        self.assertIn("Student Leadership Summit", body)
        self.assertIn("SAS AVR", body)
        self.assertIn("Monobloc Chair", body)
        self.assertIn(format_date(reservation.date, "F j, Y"), body)
        self.assertIn(format_date(reservation.start_time, "g:i A"), body)
        self.assertIn(format_date(reservation.end_time, "g:i A"), body)
        self.assertIn("Submitted on:", body)
        self.assertIn("Pending", body)

        # HTML alternative carries the same details.
        html = mail.outbox[0].alternatives[0][0]
        self.assertIn("Student Leadership Summit", html)
        self.assertIn(reservation.reservation_id, html)

    def test_pending_reservation_is_described_as_awaiting_approval(self):
        self.client.force_authenticate(self.requester)
        self._create()
        body = mail.outbox[0].body

        self.assertIn("awaiting administrator approval", body)
        self.assertIn("not yet confirmed", body)
        self.assertNotIn("has been approved", body)
        self.assertNotIn("BOOKING INSTRUCTIONS", body)
        self.assertIn("WHAT HAPPENS NEXT", body)

    # ------------------------------------------------------------------
    # 4-5: the email reflects the status that was actually saved
    # ------------------------------------------------------------------

    def test_auto_approved_reservation_is_described_as_approved(self):
        self.client.force_authenticate(self.admin)
        response = self._create(
            self._payload(
                date=(self.day + timedelta(days=7)).isoformat(),
                requester_id=self.requester.id,
            )
        )

        self.assertEqual(response.status_code, 201, response.content)
        reservation = Reservation.objects.get(pk=response.json()["id"])
        self.assertEqual(reservation.status, Reservation.Status.APPROVED)

        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.to, [self.requester.email])
        self.assertIn("Approved", sent.body)
        self.assertIn("Your booking is confirmed", sent.body)
        self.assertIn("BOOKING INSTRUCTIONS", sent.body)
        self.assertNotIn("awaiting administrator approval", sent.body)

    # ------------------------------------------------------------------
    # 6: a failed creation never sends an email
    # ------------------------------------------------------------------

    def test_failed_creation_does_not_send_email(self):
        self.client.force_authenticate(self.requester)
        first = self._create()
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(len(mail.outbox), 1)

        # Same slot again -> availability conflict, no new reservation.
        self.client.force_authenticate(
            User.objects.create_user(
                username="other", password="pass12345", role=User.Role.REQUESTER
            )
        )
        with self.captureOnCommitCallbacks(execute=True):
            conflict = self.client.post(
                "/api/reservations/", self._payload(), format="json"
            )
        self.assertEqual(conflict.status_code, 409, conflict.content)
        self.assertEqual(len(mail.outbox), 1)

        # Invalid payload -> 400, again no email.
        self.client.force_authenticate(self.requester)
        with self.captureOnCommitCallbacks(execute=True):
            invalid = self.client.post(
                "/api/reservations/",
                self._payload(
                    date=(self.day + timedelta(days=14)).isoformat(),
                    purpose="",
                ),
                format="json",
            )
        self.assertEqual(invalid.status_code, 400, invalid.content)
        self.assertEqual(len(mail.outbox), 1)

    # ------------------------------------------------------------------
    # 7: an email failure never undoes a saved reservation
    # ------------------------------------------------------------------

    def test_email_failure_keeps_reservation_and_returns_created(self):
        self.client.force_authenticate(self.requester)
        with self.assertLogs(
            "reservations.services.confirmations", level="ERROR"
        ) as logs, patch.object(
            confirmations,
            "send_booking_confirmation",
            side_effect=smtplib.SMTPException("smtp server exploded"),
        ), self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                "/api/reservations/", self._payload(), format="json"
            )

        self.assertEqual(response.status_code, 201, response.content)
        reservation = Reservation.objects.get(pk=response.json()["id"])
        self.assertEqual(reservation.status, Reservation.Status.PENDING)
        self.assertIsNone(reservation.confirmation_email_sent_at)
        self.assertIsNone(reservation.confirmation_email_claimed_at)
        self.assertEqual(len(mail.outbox), 0)
        self.assertIn("FAILED", "\n".join(logs.output))
        # The log records a safe category, never SMTP credentials.
        self.assertNotIn("password", "\n".join(logs.output).lower())

    # ------------------------------------------------------------------
    # 8: repeated requests / delivery attempts never duplicate the email
    # ------------------------------------------------------------------

    def test_repeated_requests_do_not_duplicate_the_email(self):
        self.client.force_authenticate(self.requester)
        response = self._create()
        reservation = Reservation.objects.get(pk=response.json()["id"])
        self.assertEqual(len(mail.outbox), 1)

        # A repeated frontend submit hits the same slot and is refused.
        with self.captureOnCommitCallbacks(execute=True):
            second = self.client.post(
                "/api/reservations/", self._payload(), format="json"
            )
        self.assertEqual(second.status_code, 409)
        self.assertEqual(len(mail.outbox), 1)

        # A repeated delivery attempt for the SAME reservation is a no-op.
        self.assertFalse(confirmations.deliver_booking_confirmation(reservation.pk))
        self.assertEqual(len(mail.outbox), 1)

    # ------------------------------------------------------------------
    # 9: missing / invalid requester email addresses are handled safely
    # ------------------------------------------------------------------

    def test_missing_requester_email_is_handled_safely(self):
        no_email_user = User.objects.create_user(
            username="no-email",
            password="pass12345",
            role=User.Role.REQUESTER,
            email="",
        )
        self.client.force_authenticate(no_email_user)
        response = self._create(
            self._payload(date=(self.day + timedelta(days=7)).isoformat())
        )

        self.assertEqual(response.status_code, 201, response.content)
        reservation = Reservation.objects.get(pk=response.json()["id"])
        self.assertIsNone(reservation.confirmation_email_sent_at)
        self.assertEqual(len(mail.outbox), 0)

    def test_invalid_requester_email_is_handled_safely(self):
        bad_email_user = User.objects.create_user(
            username="bad-email",
            password="pass12345",
            role=User.Role.REQUESTER,
            email="not-an-email",
        )
        self.client.force_authenticate(bad_email_user)
        response = self._create(
            self._payload(date=(self.day + timedelta(days=14)).isoformat())
        )

        self.assertEqual(response.status_code, 201, response.content)
        reservation = Reservation.objects.get(pk=response.json()["id"])
        self.assertIsNone(reservation.confirmation_email_sent_at)
        self.assertEqual(len(mail.outbox), 0)

    # ------------------------------------------------------------------
    # Opening the booking page / reading reservations sends nothing
    # ------------------------------------------------------------------

    def test_reading_reservations_does_not_send_email(self):
        self.client.force_authenticate(self.requester)
        self._create()
        self.assertEqual(len(mail.outbox), 1)

        with self.captureOnCommitCallbacks(execute=True):
            self.client.get("/api/reservations/")
            self.client.get("/api/reservations/counts/")
        self.assertEqual(len(mail.outbox), 1)
