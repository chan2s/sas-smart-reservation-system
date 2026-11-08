"""Legacy guest reservation tracking.

Guest submission has been retired in favour of the shared authenticated
reservation workflow, but links emailed before that change must keep working.
The tracking endpoint is the only unauthenticated reservation surface, so these
tests pin down exactly what it exposes: the holder of a signed token gets a
minimal status view for that one guest reservation, and nothing else.
"""

from datetime import date, time

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from facilities.models import Facility
from notifications import email_service
from reservations.models import Reservation
from reservations.services.public_tracking import (
    tracking_path_for,
    tracking_token_for,
)

User = get_user_model()

TRACK_URL = "/api/public/reservations/track/"
PUBLIC_URL = "https://reserve.norsu.edu.ph"


class PublicTrackingApiTests(TestCase):
    client_class = APIClient

    @classmethod
    def setUpTestData(cls):
        cls.facility = Facility.objects.create(
            name="Tracking Gymnasium",
            facility_type=Facility.FacilityType.GYMNASIUM,
            capacity=200,
        )

    def make_guest_reservation(self, **overrides):
        defaults = dict(
            requester=None,
            requester_type=Reservation.RequesterType.EXTERNAL,
            organization="ABC Foundation",
            organization_type=Reservation.OrganizationType.NGO,
            contact_person="Juan Dela Cruz",
            contact_email="juan@abcfoundation.org",
            event_name="Community Outreach",
            event_type=Reservation.EventType.SEMINAR,
            purpose="Community outreach programme",
            facility=self.facility,
            date=date(2026, 11, 16),
            start_time=time(9, 0),
            end_time=time(12, 0),
            expected_participants=80,
            status=Reservation.Status.PENDING,
        )
        defaults.update(overrides)
        return Reservation.objects.create(**defaults)

    def test_signed_token_returns_a_minimal_status_view(self):
        reservation = self.make_guest_reservation()

        response = self.client.post(
            TRACK_URL, {"token": tracking_token_for(reservation)}, format="json"
        )

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["reservation_id"], reservation.reservation_id)
        self.assertEqual(body["organization"], "ABC Foundation")
        self.assertEqual(body["event_name"], "Community Outreach")
        self.assertEqual(body["facility"], self.facility.name)
        self.assertEqual(body["date"], "2026-11-16")
        self.assertEqual(body["status"], "PENDING")
        # The public view never carries contact details, purpose, fees, items,
        # internal notes, or a check-in code.
        for private_field in (
            "contact_person",
            "contact_email",
            "purpose",
            "fees",
            "estimated_total",
            "resources",
            "notes",
            "checkin_code",
        ):
            self.assertNotIn(private_field, body)

    def test_invalid_tampered_and_missing_tokens_are_rejected(self):
        reservation = self.make_guest_reservation()
        token = tracking_token_for(reservation)

        for payload in ({}, {"token": ""}, {"token": "not-a-token"}, {"token": token + "x"}):
            response = self.client.post(TRACK_URL, payload, format="json")
            self.assertEqual(response.status_code, 404, payload)

    def test_token_cannot_expose_an_account_owned_reservation(self):
        requester = User.objects.create_user(
            username="external-member", password="pass12345", role=User.Role.REQUESTER
        )
        reservation = self.make_guest_reservation(requester=requester)

        response = self.client.post(
            TRACK_URL, {"token": tracking_token_for(reservation)}, format="json"
        )

        self.assertEqual(response.status_code, 404)

    def test_token_cannot_expose_a_campus_reservation(self):
        requester = User.objects.create_user(
            username="campus-member", password="pass12345", role=User.Role.REQUESTER
        )
        reservation = self.make_guest_reservation(
            requester=requester,
            requester_type=Reservation.RequesterType.CAMPUS,
            organization="",
            organization_type="",
            contact_email=requester.email,
        )

        response = self.client.post(
            TRACK_URL, {"token": tracking_token_for(reservation)}, format="json"
        )

        self.assertEqual(response.status_code, 404)

    @override_settings(PUBLIC_FRONTEND_URL=PUBLIC_URL, IS_PRODUCTION=True)
    def test_guest_email_link_uses_the_tracking_route(self):
        reservation = self.make_guest_reservation()

        self.assertEqual(
            email_service.build_reservation_url(reservation),
            f"{PUBLIC_URL}{tracking_path_for(reservation)}",
        )

    @override_settings(PUBLIC_FRONTEND_URL=PUBLIC_URL, IS_PRODUCTION=True)
    def test_account_holder_email_link_uses_the_authenticated_detail_route(self):
        requester = User.objects.create_user(
            username="account-holder", password="pass12345", role=User.Role.REQUESTER
        )
        reservation = self.make_guest_reservation(requester=requester)

        self.assertEqual(
            email_service.build_reservation_url(reservation),
            f"{PUBLIC_URL}/reservations/{reservation.pk}",
        )
