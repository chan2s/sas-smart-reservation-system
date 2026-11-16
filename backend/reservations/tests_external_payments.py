"""Administrative payment tracking for external-organization reservations.

Covers the required amount/payment type fields, derived payment status and
balance, input validation, external-only scope, and the approval warning that
must be explicitly acknowledged without ever blocking approval.
"""

from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Organization
from facilities.models import Facility, OperatingHour
from .models import Reservation

User = get_user_model()

RESERVATIONS_URL = "/api/reservations/"


class ExternalReservationPaymentTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        organization = Organization.objects.create(
            organization_name="ABC Foundation",
            organization_type=Organization.OrganizationType.NGO,
            contact_person="Juan Dela Cruz",
            contact_email="juan@abcfoundation.org",
            contact_number="09171234567",
            verification_status=Organization.VerificationStatus.APPROVED,
        )
        self.member = User.objects.create_user(
            username="juan",
            password="pass12345",
            role=User.Role.REQUESTER,
            email="juan@abcfoundation.org",
        )
        self.member.affiliation = User.Affiliation.EXTERNAL_ORGANIZATION
        self.member.organization_ref = organization
        self.member.save(update_fields=["affiliation", "organization_ref"])

        self.staff = User.objects.create_user(
            username="staff", password="pass12345", role=User.Role.STAFF
        )
        self.facility = Facility.objects.create(
            name="Gymnasium",
            facility_type=Facility.FacilityType.GYMNASIUM,
            capacity=300,
        )
        OperatingHour.objects.create(
            facility=self.facility,
            day_of_week=0,
            open_time=time(6, 0),
            close_time=time(22, 0),
        )
        self.day = timezone.localdate() + timedelta(days=1)
        while self.day.weekday() != 0:
            self.day += timedelta(days=1)

        self.client.force_authenticate(self.member)
        created = self.client.post(
            RESERVATIONS_URL,
            {
                "facility_id": self.facility.id,
                "date": self.day.isoformat(),
                "start_time": "13:00",
                "end_time": "16:00",
                "event_name": "Community Seminar",
                "event_type": "SEMINAR",
                "purpose": "Community Seminar",
                "expected_participants": 80,
                "items": [],
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.reservation = Reservation.objects.get(pk=created.json()["id"])
        self.payment_url = f"/api/reservations/{self.reservation.pk}/payments/"
        self.approve_url = f"/api/reservations/{self.reservation.pk}/approve/"

    def _save_payment(self, payment_type="FULL_PAYMENT", required="5000.00", paid="0.00"):
        self.client.force_authenticate(self.staff)
        return self.client.post(
            self.payment_url,
            {
                "payment_type": payment_type,
                "payment_required_amount": required,
                "amount_paid": paid,
            },
            format="json",
        )

    def test_payment_status_and_balance_are_derived_from_amounts(self):
        response = self._save_payment(paid="0.00")
        self.assertEqual(response.status_code, 200, response.content)
        payment = response.json()["payment"]
        self.assertEqual(payment["status"], "UNPAID")
        self.assertEqual(payment["remaining_balance"], "5000.00")

        response = self._save_payment(paid="2000.00")
        payment = response.json()["payment"]
        self.assertEqual(payment["status"], "PARTIALLY_PAID")
        self.assertEqual(payment["remaining_balance"], "3000.00")

        response = self._save_payment(paid="5000.00")
        payment = response.json()["payment"]
        self.assertEqual(payment["status"], "FULLY_PAID")
        self.assertEqual(payment["remaining_balance"], "0.00")

    def test_payment_information_persists_on_the_reservation(self):
        self._save_payment(payment_type="DOWN_PAYMENT", required="1500.00", paid="500.00")
        self.client.force_authenticate(self.staff)
        detail = self.client.get(f"/api/reservations/{self.reservation.pk}/").json()
        self.assertEqual(detail["payment"]["payment_type"], "DOWN_PAYMENT")
        self.assertEqual(detail["payment"]["required_amount"], "1500.00")
        self.assertEqual(detail["payment"]["amount_paid"], "500.00")
        self.assertEqual(detail["payment"]["remaining_balance"], "1000.00")
        self.assertEqual(detail["payment"]["status"], "PARTIALLY_PAID")

    def test_amount_paid_cannot_be_negative_or_exceed_required(self):
        response = self._save_payment(required="1000.00", paid="-1.00")
        self.assertEqual(response.status_code, 400)
        response = self._save_payment(required="1000.00", paid="1000.01")
        self.assertEqual(response.status_code, 400)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.amount_paid, 0)

    def test_internal_reservations_have_no_payment_tracking(self):
        self.reservation.requester_type = Reservation.RequesterType.CAMPUS
        self.reservation.save(update_fields=["requester_type"])
        response = self._save_payment()
        self.assertEqual(response.status_code, 400)

    def test_outstanding_payment_requires_acknowledgement_but_never_blocks(self):
        self._save_payment(paid="2000.00")
        self.client.force_authenticate(self.staff)

        warning = self.client.post(self.approve_url, {}, format="json")
        self.assertEqual(warning.status_code, 409)
        self.assertEqual(warning.json()["code"], "PAYMENT_WARNING")
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, Reservation.Status.PENDING)

        approved = self.client.post(
            self.approve_url,
            {"acknowledge_payment_warning": True},
            format="json",
        )
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual(approved.json()["status"], "APPROVED")
        # Reservation and payment statuses stay independent.
        self.assertEqual(approved.json()["payment"]["status"], "PARTIALLY_PAID")

    def test_requester_cannot_read_or_edit_payment_information(self):
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get(self.payment_url).status_code, 403)
        response = self.client.post(
            self.payment_url,
            {
                "payment_type": "FULL_PAYMENT",
                "payment_required_amount": "1000.00",
                "amount_paid": "0.00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)
