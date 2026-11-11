from datetime import time, timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from equipment.models import Equipment, EquipmentCategory
from facilities.models import Facility, OperatingHour
from reservations.models import Reservation, ReservationEditVerification


class PublicReservationEditOTPTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.facility = Facility.objects.create(
            name="Public Edit Hall", facility_type=Facility.FacilityType.AVR, capacity=100
        )
        self.day = timezone.localdate() + timedelta(days=14)
        OperatingHour.objects.create(
            facility=self.facility,
            day_of_week=self.day.weekday(),
            open_time=time(6, 0),
            close_time=time(22, 0),
        )
        category = EquipmentCategory.objects.create(name="Public edit equipment")
        self.chairs = Equipment.objects.create(
            name="Public edit chair", category=category, total_quantity=100
        )
        self.reservation = self.make_guest("SAS-PUBLIC-EDIT-1")

    def make_guest(self, reference):
        reservation = Reservation.objects.create(
            reservation_id=reference,
            requester=None,
            created_by=None,
            contact_email="registered.requester@example.com",
            contact_person="Registered Requester",
            contact_phone="09171234567",
            requester_type=Reservation.RequesterType.CAMPUS,
            organization="Community Group",
            facility=self.facility,
            date=self.day,
            start_time=time(9, 0),
            end_time=time(11, 0),
            event_name="Community Meeting",
            event_type=Reservation.EventType.MEETING,
            purpose="Community planning meeting",
            expected_participants=20,
            approval_letter_required=False,
        )
        return reservation

    def payload(self, **overrides):
        data = {
            "reservation_id": self.reservation.reservation_id,
            "facility_id": self.facility.id,
            "date": self.day.isoformat(),
            "start_time": "09:00",
            "end_time": "12:00",
            "event_name": "Updated Community Meeting",
            "event_type": "MEETING",
            "purpose": "Updated community planning meeting",
            "expected_participants": 25,
            "notes": "Updated notes",
            "contact_person": "Registered Requester",
            "contact_phone": "09171234567",
            "items": [{"equipment_id": self.chairs.id, "quantity": 25}],
        }
        data.update(overrides)
        return data

    def request_otp(self, payload=None):
        cache.clear()
        otp = {}
        with patch("notifications.email_service.send_reservation_edit_otp") as send:
            send.side_effect = lambda reservation, email, code: otp.update(email=email, code=code) or True
            response = self.client.post(
                "/api/public/reservations/request-edit-otp/",
                payload or self.payload(),
                format="json",
            )
        return response, otp

    def verify(self, reference, session, code):
        cache.clear()
        return self.client.post(
            "/api/public/reservations/verify-edit-otp/",
            {"reservation_id": reference, "verification_session": session, "otp": code},
            format="json",
        )

    def test_public_edit_details_omits_email_and_exposes_eligible_state(self):
        cache.clear()
        tracked = self.client.post(
            "/api/public/reservations/track/",
            {"reservation_id": self.reservation.reservation_id},
            format="json",
        )
        self.assertEqual(tracked.status_code, 200)
        self.assertTrue(tracked.json()["can_edit"])
        cache.clear()
        details = self.client.post(
            "/api/public/reservations/edit-details/",
            {"reservation_id": self.reservation.reservation_id},
            format="json",
        )
        self.assertEqual(details.status_code, 200)
        self.assertNotIn("contact_email", details.json())
        self.assertEqual(details.json()["event_name"], self.reservation.event_name)

    def test_public_edit_preserves_facility_capacity_validation(self):
        response, _sent = self.request_otp(self.payload(expected_participants=101))
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("expected_participants", response.json())
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.expected_participants, 20)
        self.assertFalse(ReservationEditVerification.objects.filter(reservation=self.reservation).exists())

    def test_public_request_sends_masked_destination_and_correct_code_applies_atomically(self):
        response, sent = self.request_otp()
        self.assertEqual(response.status_code, 202, response.content)
        body = response.json()
        self.assertEqual(body["email_hint"], "r******@example.com")
        self.assertNotIn("registered.requester@example.com", response.content.decode())
        self.assertNotIn("code", body)
        self.assertEqual(sent["email"], "registered.requester@example.com")
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.event_name, "Community Meeting")

        verification_id = ReservationEditVerification.objects.get(reservation=self.reservation).pk
        result = self.verify(self.reservation.reservation_id, body["verification_session"], sent["code"])
        self.assertEqual(result.status_code, 200, result.content)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.event_name, "Updated Community Meeting")
        self.assertEqual(self.reservation.end_time, time(12, 0))
        self.assertEqual(self.reservation.status, Reservation.Status.PENDING)
        self.assertEqual(self.reservation.items.get().quantity, 25)
        self.assertTrue(self.reservation.events.filter(event_type="UPDATED").exists())
        self.assertFalse(ReservationEditVerification.objects.filter(pk=verification_id).exists())
        replay = self.verify(self.reservation.reservation_id, body["verification_session"], sent["code"])
        self.assertEqual(replay.status_code, 400)

    def test_incorrect_and_expired_codes_do_not_apply_pending_changes(self):
        response, sent = self.request_otp()
        session = response.json()["verification_session"]
        wrong = self.verify(self.reservation.reservation_id, session, "000000" if sent["code"] != "000000" else "000001")
        self.assertEqual(wrong.status_code, 400)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.event_name, "Community Meeting")
        verification = ReservationEditVerification.objects.get(reservation=self.reservation)
        verification.expires_at = timezone.now() - timedelta(seconds=1)
        verification.save(update_fields=["expires_at"])
        expired = self.verify(self.reservation.reservation_id, session, sent["code"])
        self.assertEqual(expired.status_code, 400)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.event_name, "Community Meeting")

    def test_resend_replaces_code_and_attempt_limit_is_enforced(self):
        response, first = self.request_otp()
        session = response.json()["verification_session"]
        cache.clear()
        cooldown = self.client.post(
            "/api/public/reservations/resend-edit-otp/",
            {"reservation_id": self.reservation.reservation_id, "verification_session": session},
            format="json",
        )
        self.assertEqual(cooldown.status_code, 429)
        verification = ReservationEditVerification.objects.get(reservation=self.reservation)
        verification.resend_available_at = timezone.now() - timedelta(seconds=1)
        verification.save(update_fields=["resend_available_at"])
        cache.clear()
        with patch("notifications.email_service.send_reservation_edit_otp") as send:
            send.side_effect = lambda reservation, email, code: setattr(self, "resent_code", code) or True
            resent = self.client.post(
                "/api/public/reservations/resend-edit-otp/",
                {"reservation_id": self.reservation.reservation_id, "verification_session": session},
                format="json",
            )
        self.assertEqual(resent.status_code, 202, resent.content)
        self.assertNotEqual(first["code"], self.resent_code)
        old_code = self.verify(self.reservation.reservation_id, session, first["code"])
        self.assertEqual(old_code.status_code, 400)
        incorrect_code = "000000" if self.resent_code != "000000" else "000001"
        for _ in range(5):
            cache.clear()
            response = self.verify(self.reservation.reservation_id, session, incorrect_code)
            self.assertEqual(response.status_code, 400)
        verification.refresh_from_db()
        self.assertEqual(verification.attempts, 5)
        blocked_correct_code = self.verify(self.reservation.reservation_id, session, self.resent_code)
        self.assertEqual(blocked_correct_code.status_code, 400)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.event_name, "Community Meeting")

    def test_verification_session_cannot_be_used_for_another_reservation(self):
        other = self.make_guest("SAS-PUBLIC-EDIT-2")
        response, sent = self.request_otp()
        session = response.json()["verification_session"]
        mismatch = self.verify(other.reservation_id, session, sent["code"])
        self.assertEqual(mismatch.status_code, 400)
        other.refresh_from_db()
        self.assertEqual(other.event_name, "Community Meeting")

    def test_availability_is_rechecked_before_apply(self):
        response, sent = self.request_otp()
        conflict = Reservation.objects.create(
            requester=None,
            facility=self.facility,
            date=self.day,
            start_time=time(11, 0),
            end_time=time(12, 30),
            event_name="Approved conflict",
            event_type=Reservation.EventType.MEETING,
            expected_participants=5,
            status=Reservation.Status.APPROVED,
            approval_letter_required=False,
        )
        result = self.verify(self.reservation.reservation_id, response.json()["verification_session"], sent["code"])
        self.assertEqual(result.status_code, 409, result.content)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.end_time, time(11, 0))
        self.assertEqual(self.reservation.event_name, "Community Meeting")
        conflict.refresh_from_db()
