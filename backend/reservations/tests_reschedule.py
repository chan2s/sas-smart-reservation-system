from datetime import time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.template.loader import render_to_string
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from facilities.models import Facility, OperatingHour
from reservations.models import (
    PricingRule,
    Reservation,
    RescheduleRequest,
    RescheduleVerification,
)


class RescheduleWorkflowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.facility = Facility.objects.create(
            name="Reschedule Hall",
            facility_type=Facility.FacilityType.AVR,
            capacity=100,
        )
        self.day = timezone.localdate() + timedelta(days=14)
        OperatingHour.objects.create(
            facility=self.facility,
            day_of_week=self.day.weekday(),
            open_time=time(6, 0),
            close_time=time(22, 0),
        )
        self.reservation = self.make_reservation()

    def make_reservation(self, *, reference=None, requester_type=None, status=None):
        return Reservation.objects.create(
            reservation_id=reference or "GSO-RESCHED-1",
            requester=None,
            created_by=None,
            contact_email="requester@example.com",
            contact_person="Requester",
            requester_type=requester_type or Reservation.RequesterType.CAMPUS,
            organization="Community Group",
            facility=self.facility,
            date=self.day,
            start_time=time(9, 0),
            end_time=time(11, 0),
            event_name="Community Meeting",
            event_type=Reservation.EventType.MEETING,
            purpose="Planning",
            expected_participants=20,
            approval_letter_required=False,
            status=status or Reservation.Status.APPROVED,
        )

    def payload(self, **overrides):
        data = {
            "reservation_id": self.reservation.reservation_id,
            "requested_date": self.day.isoformat(),
            "requested_start_time": "13:00",
            "requested_end_time": "15:00",
            "reason": "Facility conflict on the original time.",
        }
        data.update(overrides)
        return data

    def request_otp(self, payload=None, reservation=None):
        cache.clear()
        reservation = reservation or self.reservation
        sent = {}
        with patch(
            "notifications.email_service.send_reschedule_otp"
        ) as send:
            send.side_effect = (
                lambda current, email, code: sent.update(email=email, code=code) or True
            )
            response = self.client.post(
                "/api/public/reservations/request-reschedule-otp/",
                payload or self.payload(reservation_id=reservation.reservation_id),
                format="json",
            )
        return response, sent

    def verify(self, reference, session, code):
        cache.clear()
        return self.client.post(
            "/api/public/reservations/verify-reschedule-otp/",
            {
                "reservation_id": reference,
                "verification_session": session,
                "otp": code,
            },
            format="json",
        )

    def create_pending(self):
        response, sent = self.request_otp()
        self.assertEqual(response.status_code, 202, response.content)
        result = self.verify(
            self.reservation.reservation_id,
            response.json()["verification_session"],
            sent["code"],
        )
        self.assertEqual(result.status_code, 200, result.content)
        return RescheduleRequest.objects.get(reservation=self.reservation)

    def admin(self):
        user = User.objects.create_user(
            username="gso-admin", password="pass12345", role=User.Role.ADMIN
        )
        self.client.force_authenticate(user=user)
        return user

    def test_tracking_exposes_reschedule_eligibility_without_email(self):
        cache.clear()
        response = self.client.post(
            "/api/public/reservations/track/",
            {"reservation_id": self.reservation.reservation_id},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["reschedule"]["can_request"])
        self.assertIsNone(body["reschedule"]["request"])
        self.assertNotIn("requester@example.com", response.content.decode())

    def test_pending_reservation_cannot_request_reschedule(self):
        self.reservation.status = Reservation.Status.PENDING
        self.reservation.save(update_fields=["status"])
        response, _sent = self.request_otp()
        self.assertEqual(response.status_code, 404)

    def test_otp_is_sent_and_request_is_not_created_before_verification(self):
        response, sent = self.request_otp()
        self.assertEqual(response.status_code, 202, response.content)
        body = response.json()
        self.assertNotIn("requester@example.com", response.content.decode())
        self.assertIn("*", body["email_hint"])
        self.assertEqual(sent["email"], "requester@example.com")
        self.assertFalse(RescheduleRequest.objects.exists())
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.date, self.day)
        self.assertEqual(self.reservation.start_time, time(9, 0))

    def test_correct_otp_creates_pending_request_and_preserves_reservation(self):
        request_row = self.create_pending()
        self.reservation.refresh_from_db()
        self.assertEqual(request_row.status, RescheduleRequest.Status.PENDING)
        self.assertEqual(self.reservation.start_time, time(9, 0))
        self.assertEqual(self.reservation.status, Reservation.Status.APPROVED)
        self.assertTrue(
            self.reservation.events.filter(event_type="RESCHEDULE_REQUESTED").exists()
        )
        tracked = self.client.post(
            "/api/public/reservations/track/",
            {"reservation_id": self.reservation.reservation_id},
            format="json",
        ).json()
        self.assertEqual(tracked["reschedule"]["request"]["status"], "PENDING")
        self.assertFalse(tracked["reschedule"]["can_request"])

    def test_reschedule_emails_use_gso_reserve_branding(self):
        request_row = self.create_pending()
        context = {
            "site_name": "GSO RESERVE",
            "reservation_id": self.reservation.reservation_id,
            "event_name": self.reservation.event_name,
            "facility": self.reservation.facility.name,
            "current_date": self.reservation.date,
            "current_start_time": self.reservation.start_time,
            "current_end_time": self.reservation.end_time,
            "requested_date": request_row.requested_date,
            "requested_start_time": request_row.requested_start_time,
            "requested_end_time": request_row.requested_end_time,
            "reason": request_row.reason,
            "rejection_reason": "Not available.",
            "admin_message": "Please clarify.",
        }
        for name in (
            "reschedule_otp",
            "reschedule_submitted",
            "reschedule_approved",
            "reschedule_rejected",
            "reschedule_info_requested",
        ):
            html = render_to_string(f"emails/{name}.html", context)
            text = render_to_string(f"emails/{name}.txt", context)
            self.assertIn("GSO RESERVE", html)
            self.assertIn("GSO RESERVE", text)
            self.assertNotIn("SAS", html)
            self.assertNotIn("SAS", text)

    def test_duplicate_pending_request_is_refused(self):
        self.create_pending()
        response, _sent = self.request_otp()
        self.assertEqual(response.status_code, 409)

    def test_incorrect_expired_and_replayed_codes_are_rejected(self):
        response, sent = self.request_otp()
        session = response.json()["verification_session"]
        wrong = "000000" if sent["code"] != "000000" else "000001"
        self.assertEqual(self.verify(self.reservation.reservation_id, session, wrong).status_code, 400)
        verification = RescheduleVerification.objects.get(reservation=self.reservation)
        verification.expires_at = timezone.now() - timedelta(seconds=1)
        verification.save(update_fields=["expires_at"])
        self.assertEqual(
            self.verify(self.reservation.reservation_id, session, sent["code"]).status_code,
            400,
        )
        self.assertFalse(RescheduleRequest.objects.exists())

    def test_verified_session_cannot_be_replayed(self):
        response, sent = self.request_otp()
        session = response.json()["verification_session"]
        first = self.verify(self.reservation.reservation_id, session, sent["code"])
        self.assertEqual(first.status_code, 200, first.content)
        replay = self.verify(self.reservation.reservation_id, session, sent["code"])
        self.assertEqual(replay.status_code, 400)
        self.assertEqual(RescheduleRequest.objects.count(), 1)

    def test_resend_cooldown_and_new_code_invalidates_previous_code(self):
        response, first = self.request_otp()
        session = response.json()["verification_session"]
        self.assertEqual(self.request_otp()[0].status_code, 429)
        RescheduleVerification.objects.filter(reservation=self.reservation).update(
            resend_available_at=timezone.now() - timedelta(seconds=1)
        )
        second_response, second = self.request_otp()
        self.assertEqual(second_response.status_code, 202, second_response.content)
        self.assertNotEqual(first["code"], second["code"])
        self.assertEqual(
            self.verify(self.reservation.reservation_id, session, first["code"]).status_code,
            400,
        )
        self.assertEqual(
            self.verify(
                self.reservation.reservation_id,
                second_response.json()["verification_session"],
                second["code"],
            ).status_code,
            200,
        )

    def test_availability_is_checked_before_an_otp_is_issued(self):
        Reservation.objects.create(
            requester=None,
            facility=self.facility,
            date=self.day,
            start_time=time(13, 0),
            end_time=time(15, 0),
            event_name="Approved conflict",
            event_type=Reservation.EventType.MEETING,
            expected_participants=5,
            status=Reservation.Status.APPROVED,
            approval_letter_required=False,
        )
        response, _sent = self.request_otp()
        self.assertEqual(response.status_code, 409)
        self.assertFalse(RescheduleVerification.objects.exists())

    def test_session_cannot_be_replayed_against_another_reservation(self):
        other = self.make_reservation(reference="GSO-RESCHED-2")
        response, sent = self.request_otp()
        self.assertEqual(
            self.verify(
                other.reservation_id,
                response.json()["verification_session"],
                sent["code"],
            ).status_code,
            400,
        )

    def test_admin_approval_updates_schedule_in_place_and_recalculates_fees(self):
        external = self.reservation
        external.requester_type = Reservation.RequesterType.EXTERNAL
        external.save(update_fields=["requester_type"])
        PricingRule.objects.update(is_active=False)
        PricingRule.objects.create(
            fee_type=PricingRule.FeeType.FACILITY,
            facility_type=Facility.FacilityType.AVR,
            unit=PricingRule.Unit.FLAT,
            unit_price=Decimal("1000.00"),
            included_hours=Decimal("9.00"),
        )
        PricingRule.objects.create(
            fee_type=PricingRule.FeeType.OVERTIME,
            facility_type=Facility.FacilityType.AVR,
            unit=PricingRule.Unit.HOUR,
            unit_price=Decimal("100.00"),
            included_hours=Decimal("9.00"),
        )
        from reservations.services.pricing import snapshot_reservation_fees

        snapshot_reservation_fees(external)
        external.refresh_from_db()
        original_total = external.estimated_total
        original_reference = external.reservation_id
        original_id = external.pk

        payload = self.payload(
            reservation_id=external.reservation_id,
            requested_start_time="08:00",
            requested_end_time="19:00",
        )
        response, sent = self.request_otp(payload, reservation=external)
        self.assertEqual(response.status_code, 202, response.content)
        verified = self.verify(
            external.reservation_id,
            response.json()["verification_session"],
            sent["code"],
        )
        self.assertEqual(verified.status_code, 200, verified.content)
        request_row = RescheduleRequest.objects.get(reservation=external)

        admin = self.admin()
        with patch(
            "notifications.email_service.send_reschedule_approved"
        ) as send_approved:
            with self.captureOnCommitCallbacks(execute=True):
                approved = self.client.post(
                    f"/api/reservations/{external.pk}/approve-reschedule/",
                    {"request_id": request_row.pk},
                    format="json",
                )
        self.assertTrue(send_approved.called)
        self.assertEqual(approved.status_code, 200, approved.content)
        external.refresh_from_db()
        request_row.refresh_from_db()
        self.assertEqual(external.pk, original_id)
        self.assertEqual(external.reservation_id, original_reference)
        self.assertEqual(external.start_time, time(8, 0))
        self.assertEqual(external.end_time, time(19, 0))
        self.assertEqual(external.status, Reservation.Status.APPROVED)
        self.assertEqual(request_row.status, RescheduleRequest.Status.APPROVED)
        self.assertEqual(request_row.reviewed_by, admin)
        self.assertNotEqual(external.estimated_total, original_total)
        self.assertEqual(
            external.payment_required_amount,
            (external.estimated_total * Decimal("0.50")).quantize(Decimal("0.01")),
        )
        self.assertTrue(
            external.events.filter(event_type="RESCHEDULED").exists()
        )

    def test_approval_is_refused_when_requested_slot_became_unavailable(self):
        request_row = self.create_pending()
        Reservation.objects.create(
            requester=None,
            facility=self.facility,
            date=self.day,
            start_time=time(13, 0),
            end_time=time(15, 0),
            event_name="Later conflict",
            event_type=Reservation.EventType.MEETING,
            expected_participants=5,
            status=Reservation.Status.APPROVED,
            approval_letter_required=False,
        )
        self.admin()
        response = self.client.post(
            f"/api/reservations/{self.reservation.pk}/approve-reschedule/",
            {"request_id": request_row.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 409, response.content)
        self.reservation.refresh_from_db()
        request_row.refresh_from_db()
        self.assertEqual(self.reservation.start_time, time(9, 0))
        self.assertEqual(request_row.status, RescheduleRequest.Status.PENDING)

    def test_admin_reject_and_info_actions_leave_reservation_unchanged(self):
        request_row = self.create_pending()
        self.admin()
        rejected = self.client.post(
            f"/api/reservations/{self.reservation.pk}/reject-reschedule/",
            {"request_id": request_row.pk, "reason": "Facility unavailable."},
            format="json",
        )
        self.assertEqual(rejected.status_code, 200, rejected.content)
        request_row.refresh_from_db()
        self.reservation.refresh_from_db()
        self.assertEqual(request_row.status, RescheduleRequest.Status.REJECTED)
        self.assertEqual(request_row.rejection_reason, "Facility unavailable.")
        self.assertEqual(self.reservation.start_time, time(9, 0))

        tracked = self.client.post(
            "/api/public/reservations/track/",
            {"reservation_id": self.reservation.reservation_id},
            format="json",
        ).json()
        self.assertEqual(
            tracked["reschedule"]["request"]["rejection_reason"],
            "Facility unavailable.",
        )

    def test_admin_can_request_more_information_without_moving_reservation(self):
        request_row = self.create_pending()
        self.admin()
        with patch(
            "notifications.email_service.send_reschedule_info_requested"
        ) as send:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    f"/api/reservations/{self.reservation.pk}/request-reschedule-info/",
                    {
                        "request_id": request_row.pk,
                        "message": "Please confirm the number of participants.",
                    },
                    format="json",
                )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(send.called)
        request_row.refresh_from_db()
        self.reservation.refresh_from_db()
        self.assertEqual(request_row.status, RescheduleRequest.Status.INFO_REQUIRED)
        self.assertEqual(
            request_row.admin_message, "Please confirm the number of participants."
        )
        self.assertEqual(self.reservation.start_time, time(9, 0))
        tracked = self.client.post(
            "/api/public/reservations/track/",
            {"reservation_id": self.reservation.reservation_id},
            format="json",
        ).json()
        self.assertEqual(
            tracked["reschedule"]["request"]["admin_message"],
            "Please confirm the number of participants.",
        )

    def test_non_staff_cannot_review_a_reschedule_request(self):
        request_row = self.create_pending()
        user = User.objects.create_user(
            username="plain-requester", password="pass12345", role=User.Role.REQUESTER
        )
        self.client.force_authenticate(user=user)
        response = self.client.post(
            f"/api/reservations/{self.reservation.pk}/reject-reschedule/",
            {"request_id": request_row.pk, "reason": "No."},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        request_row.refresh_from_db()
        self.assertEqual(request_row.status, RescheduleRequest.Status.PENDING)
