"""Tests for the administrator "Send Revision Request" email workflow."""

from datetime import date, time

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from rest_framework.test import APIClient

from facilities.models import Facility, OperatingHour
from reservations.models import Reservation, ReservationEvent
from reservations.services import workflow

User = get_user_model()


class RevisionRequestEmailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username="revision-admin",
            password="pass12345",
            role=User.Role.ADMIN,
            first_name="Ada",
            last_name="Admin",
        )
        cls.requester = User.objects.create_user(
            username="revision-requester",
            password="pass12345",
            role=User.Role.REQUESTER,
            first_name="Juan",
            last_name="Dela Cruz",
            email="juan@campus.edu",
        )
        cls.facility = Facility.objects.create(
            name="Revision Test AVR",
            facility_type=Facility.FacilityType.AVR,
            capacity=80,
        )
        OperatingHour.objects.create(
            facility=cls.facility,
            day_of_week=0,
            open_time=time(6, 0),
            close_time=time(22, 0),
        )

    def setUp(self):
        self.reservation = Reservation.objects.create(
            requester=self.requester,
            requester_type=Reservation.RequesterType.CAMPUS,
            # Deliberately different from the account email: notifications must
            # go to the registered requester, not this snapshot field.
            contact_email="stale-contact@example.com",
            event_name="Research Symposium",
            event_type=Reservation.EventType.ACADEMIC,
            facility=self.facility,
            date=date(2026, 12, 3),
            start_time=time(9, 0),
            end_time=time(12, 0),
            status=Reservation.Status.PENDING,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def post_revision(self, **payload):
        body = {"message": "Please adjust the end time to 5:00 PM."}
        body.update(payload)
        return self.client.post(
            f"/api/reservations/{self.reservation.pk}/request_changes/",
            body,
            format="json",
        )

    def test_sends_email_and_records_the_communication(self):
        response = self.post_revision()

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertTrue(body["revision_email_sent"])
        self.assertEqual(body["requester_email"], "juan@campus.edu")
        self.assertIn("juan@campus.edu", body["revision_email_detail"])

        # The workflow decision is unchanged: the reservation is still awaiting
        # review — neither approved nor rejected.
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, Reservation.Status.PENDING)

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ["juan@campus.edu"])
        self.assertEqual(
            email.subject,
            f"Action Required: Reservation Revision – {self.reservation.reservation_id}",
        )
        self.assertIn("Action Required: Reservation Revision", email.subject)
        self.assertIn(self.reservation.reservation_id, email.body)
        self.assertIn("Research Symposium", email.body)
        self.assertIn("Please adjust the end time to 5:00 PM.", email.body)
        self.assertIn("coordinate with the SAS Office", email.body)

        event = ReservationEvent.objects.get(
            reservation=self.reservation,
            event_type=ReservationEvent.EventType.CHANGES_REQUESTED,
        )
        self.assertEqual(event.actor, self.admin)
        self.assertEqual(event.recipient_email, "juan@campus.edu")
        self.assertEqual(event.message, "Please adjust the end time to 5:00 PM.")
        self.assertIsNotNone(event.created_at)

    def test_custom_subject_is_used(self):
        response = self.post_revision(subject="Room setup needs revision")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Room setup needs revision")

    def test_additional_revision_requests_are_allowed(self):
        self.assertEqual(self.post_revision().status_code, 200)
        self.assertEqual(
            self.post_revision(message="Please also add two more tables.").status_code,
            200,
        )

        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(
            ReservationEvent.objects.filter(
                reservation=self.reservation,
                event_type=ReservationEvent.EventType.CHANGES_REQUESTED,
            ).count(),
            2,
        )

    def test_blank_message_is_rejected_without_sending(self):
        response = self.post_revision(message="   ")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(
            ReservationEvent.objects.filter(
                reservation=self.reservation,
                event_type=ReservationEvent.EventType.CHANGES_REQUESTED,
            ).exists()
        )

    def test_subject_with_line_breaks_is_rejected(self):
        response = self.post_revision(subject="Hello\nBcc: evil@example.com")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(mail.outbox), 0)

    def test_reservation_without_an_email_reports_failure_but_records_request(self):
        self.requester.email = ""
        self.requester.save(update_fields=["email"])
        self.reservation.contact_email = ""
        self.reservation.save(update_fields=["contact_email"])

        response = self.post_revision()

        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.json()["revision_email_sent"])
        self.assertIn("no email address on file", response.json()["revision_email_detail"])
        self.assertEqual(len(mail.outbox), 0)
        event = ReservationEvent.objects.get(
            reservation=self.reservation,
            event_type=ReservationEvent.EventType.CHANGES_REQUESTED,
        )
        self.assertEqual(event.recipient_email, "")

    def test_non_staff_cannot_send_a_revision_request(self):
        self.client.force_authenticate(self.requester)
        response = self.post_revision()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(mail.outbox), 0)

    def test_workflow_returns_delivery_result(self):
        sent, error = workflow.request_changes(
            self.reservation,
            self.admin,
            "Please add the requested equipment.",
            subject="",
        )

        self.assertTrue(sent)
        self.assertIsNone(error)
        self.assertEqual(len(mail.outbox), 1)
