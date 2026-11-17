"""External-organization payment tracking and approval safeguards.

The required amount is never entered by staff: it is derived from the
reservation's snapshotted official rental total. Down payment is exactly 50%
and full payment is 100%. These tests cover those calculations, the derived
payment status/balance, input validation, external-only scope, and the
approval acknowledgement that never silently approves an unpaid reservation.
"""

from datetime import time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Organization
from facilities.models import Facility, OperatingHour
from .models import Reservation
from .services.payments import approval_warning

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

    # -- helpers ---------------------------------------------------------
    def _set_total(self, total="10000.00", payment_type="DOWN_PAYMENT"):
        self.reservation.estimated_total = Decimal(total)
        self.reservation.payment_type = payment_type
        self.reservation.save(
            update_fields=["estimated_total", "payment_type", "updated_at"]
        )
        self.reservation.refresh_from_db()
        return self.reservation

    def _save_payment(self, payment_type="DOWN_PAYMENT", paid="0.00", **extra):
        self.client.force_authenticate(self.staff)
        return self.client.post(
            self.payment_url,
            {
                "payment_type": payment_type,
                "amount_paid": paid,
                **extra,
            },
            format="json",
        )

    def _approve(self, **body):
        self.client.force_authenticate(self.staff)
        return self.client.post(self.approve_url, body, format="json")

    # -- automatic requirement ------------------------------------------
    def test_down_payment_is_automatically_half_the_rental_total(self):
        self._set_total("10000.00", "DOWN_PAYMENT")
        self.assertEqual(self.reservation.required_payment_amount, Decimal("5000.00"))
        self.assertEqual(self.reservation.payment_required_amount, Decimal("5000.00"))

        self.client.force_authenticate(self.staff)
        detail = self.client.get(RESERVATIONS_URL + f"{self.reservation.pk}/").json()
        payment = detail["payment"]
        self.assertEqual(payment["total_amount"], "10000.00")
        self.assertEqual(payment["down_payment_amount"], "5000.00")
        self.assertEqual(payment["required_amount"], "5000.00")
        self.assertEqual(payment["payment_type"], "DOWN_PAYMENT")
        self.assertEqual(payment["status"], "UNPAID")

    def test_full_payment_is_automatically_the_whole_total(self):
        self._set_total("12000.00", "FULL_PAYMENT")
        self.assertEqual(self.reservation.required_payment_amount, Decimal("12000.00"))

        response = self._save_payment(payment_type="FULL_PAYMENT", paid="12000.00")
        self.assertEqual(response.status_code, 200, response.content)
        payment = response.json()["payment"]
        self.assertEqual(payment["required_amount"], "12000.00")
        self.assertEqual(payment["status"], "FULLY_PAID")

    def test_total_change_recalculates_requirement_without_touching_payment(self):
        self._set_total("10000.00", "DOWN_PAYMENT")
        response = self._save_payment(paid="2000.00")
        self.assertEqual(response.status_code, 200, response.content)

        self._set_total("12000.00", "DOWN_PAYMENT")
        self.assertEqual(self.reservation.required_payment_amount, Decimal("6000.00"))
        self.assertEqual(self.reservation.amount_paid, Decimal("2000.00"))
        self.assertEqual(self.reservation.remaining_balance, Decimal("4000.00"))

    def test_client_cannot_override_the_required_amount(self):
        self._set_total("10000.00", "DOWN_PAYMENT")
        response = self._save_payment(paid="0.00", payment_required_amount="1.00")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["payment"]["required_amount"], "5000.00")
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.payment_required_amount, Decimal("5000.00"))

    def test_payment_status_and_balance_follow_the_required_amount(self):
        self._set_total("10000.00", "DOWN_PAYMENT")

        unpaid = self._save_payment(paid="0.00").json()["payment"]
        self.assertEqual(unpaid["status"], "UNPAID")
        self.assertEqual(unpaid["remaining_balance"], "5000.00")

        partial = self._save_payment(paid="2000.00").json()["payment"]
        self.assertEqual(partial["status"], "PARTIALLY_PAID")
        self.assertEqual(partial["remaining_balance"], "3000.00")

        complete = self._save_payment(paid="5000.00").json()["payment"]
        self.assertEqual(complete["status"], "FULLY_PAID")
        self.assertEqual(complete["remaining_balance"], "0.00")

    def test_amount_paid_cannot_be_negative_or_exceed_total_price(self):
        self._set_total("10000.00", "DOWN_PAYMENT")
        self.assertEqual(self._save_payment(paid="-1.00").status_code, 400)
        self.assertEqual(self._save_payment(paid="10000.01").status_code, 400)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.amount_paid, Decimal("0.00"))

    # -- approval scenarios ---------------------------------------------
    def test_unpaid_external_reservation_requires_acknowledgement(self):
        self._set_total("10000.00", "DOWN_PAYMENT")
        warning = self._approve()

        self.assertEqual(warning.status_code, 409)
        body = warning.json()
        self.assertEqual(body["code"], "PAYMENT_WARNING")
        self.assertEqual(body["payment"]["total_amount"], "10000.00")
        self.assertEqual(body["payment"]["down_payment_amount"], "5000.00")
        self.assertEqual(body["payment"]["required_amount"], "5000.00")
        self.assertEqual(body["payment"]["amount_paid"], "0.00")
        self.assertEqual(body["payment"]["remaining_balance"], "5000.00")
        self.assertEqual(body["payment"]["status"], "UNPAID")

        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, Reservation.Status.PENDING)

    def test_admin_can_approve_without_payment_while_preserving_payment_state(self):
        self._set_total("10000.00", "DOWN_PAYMENT")
        approved = self._approve(acknowledge_payment_warning=True)

        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual(approved.json()["status"], "APPROVED")
        self.assertEqual(approved.json()["payment"]["status"], "UNPAID")
        self.assertEqual(approved.json()["payment"]["amount_paid"], "0.00")
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.amount_paid, Decimal("0.00"))
        self.assertEqual(self.reservation.status, Reservation.Status.APPROVED)

    def test_partial_payment_warns_with_remaining_downpayment(self):
        self._set_total("10000.00", "DOWN_PAYMENT")
        self.assertEqual(self._save_payment(paid="2000.00").status_code, 200)

        warning = self._approve()
        self.assertEqual(warning.status_code, 409)
        payment = warning.json()["payment"]
        self.assertEqual(payment["status"], "PARTIALLY_PAID")
        self.assertEqual(payment["remaining_balance"], "3000.00")

    def test_complete_downpayment_approves_without_warning(self):
        self._set_total("10000.00", "DOWN_PAYMENT")
        self.assertEqual(self._save_payment(paid="5000.00").status_code, 200)

        approved = self._approve()
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual(approved.json()["payment"]["status"], "FULLY_PAID")
        self.assertIsNone(approved.json()["payment"]["approval_warning"])

    def test_internal_reservation_approval_is_unchanged(self):
        self.reservation.requester_type = Reservation.RequesterType.CAMPUS
        self.reservation.save(update_fields=["requester_type", "updated_at"])
        self.client.force_authenticate(self.staff)

        approved = self.client.post(self.approve_url, {}, format="json")
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual(approved.json()["status"], "APPROVED")
        self.assertIsNone(approved.json()["payment"])

    def test_external_reservation_without_a_total_never_warns(self):
        self._set_total("0.00", "DOWN_PAYMENT")
        self.assertEqual(self.reservation.required_payment_amount, Decimal("0.00"))
        self.assertIsNone(approval_warning(self.reservation))

        approved = self._approve()
        self.assertEqual(approved.status_code, 200, approved.content)

    # -- authorization ---------------------------------------------------
    def test_requester_cannot_read_or_edit_payment_information(self):
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get(self.payment_url).status_code, 403)
        response = self.client.post(
            self.payment_url,
            {"payment_type": "FULL_PAYMENT", "amount_paid": "0.00"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
