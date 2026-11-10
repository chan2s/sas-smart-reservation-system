"""Web Push API and delivery tests. Push provider calls are always mocked."""

import json
import base64
from unittest import mock
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from cryptography.hazmat.primitives.asymmetric import ec

from notifications.models import Notification, PushSubscription
from notifications.services import notify, notify_staff, send_push_to_user

User = get_user_model()
_TEST_PRIVATE_SCALAR = (7).to_bytes(32, "big")
_TEST_PRIVATE_KEY = ec.derive_private_key(7, ec.SECP256R1())
_TEST_PUBLIC_KEY = base64.urlsafe_b64encode(
    _TEST_PRIVATE_KEY.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
).decode().rstrip("=")
_TEST_PRIVATE_KEY_ENCODED = base64.urlsafe_b64encode(_TEST_PRIVATE_SCALAR).decode().rstrip("=")
_TEST_VAPID_SETTINGS = {
    "VAPID_PUBLIC_KEY": _TEST_PUBLIC_KEY,
    "VAPID_PRIVATE_KEY": _TEST_PRIVATE_KEY_ENCODED,
    "VAPID_SUBJECT": "mailto:test@example.test",
    "VAPID_CLAIMS_EMAIL": "mailto:test@example.test",
}


class PushApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("push-user", password="password123")
        self.other = User.objects.create_user("push-other", password="password123")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def payload(self, endpoint="https://push.example.test/one"):
        public_key = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )
        return {
            "device_name": "Chrome on Windows",
            "endpoint": endpoint,
            "p256dh": base64.urlsafe_b64encode(public_key).decode().rstrip("="),
            "auth": base64.urlsafe_b64encode(b"a" * 16).decode().rstrip("="),
        }

    def test_register_duplicate_and_multiple_devices(self):
        first = self.client.post("/api/push/subscriptions/", self.payload("https://fcm.googleapis.com/one"), format="json")
        duplicate = self.client.post("/api/push/subscriptions/", self.payload("https://fcm.googleapis.com/one"), format="json")
        second = self.client.post("/api/push/subscriptions/", self.payload("https://fcm.googleapis.com/two"), format="json")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(duplicate.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(PushSubscription.objects.filter(user=self.user).count(), 2)
        listed = self.client.get("/api/push/subscriptions/").json()
        self.assertEqual(len(listed), 2)
        self.assertNotIn("endpoint", listed[0])
        self.assertNotIn("p256dh", listed[0])
        self.assertNotIn("auth", listed[0])

    def test_cannot_claim_another_accounts_endpoint(self):
        payload = self.payload("https://fcm.googleapis.com/one")
        PushSubscription.objects.create(user=self.other, **payload)
        response = self.client.post("/api/push/subscriptions/", payload, format="json")
        self.assertEqual(response.status_code, 400)

    def test_device_removal_is_owner_scoped(self):
        device = PushSubscription.objects.create(user=self.user, **self.payload("https://fcm.googleapis.com/one"))
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.delete(f"/api/push/subscriptions/{device.pk}/").status_code, 404)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.delete(f"/api/push/subscriptions/{device.pk}/").status_code, 204)

    def test_production_rejects_non_https_endpoints(self):
        with override_settings(DEBUG=False):
            response = self.client.post("/api/push/subscriptions/", self.payload("http://push.example.test/one"), format="json")
        self.assertEqual(response.status_code, 400)

    def test_rejects_untrusted_push_endpoint(self):
        response = self.client.post(
            "/api/push/subscriptions/",
            self.payload("https://attacker.invalid/collect"),
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_rejects_invalid_subscription_key(self):
        payload = self.payload("https://fcm.googleapis.com/invalid-key")
        payload["p256dh"] = base64.urlsafe_b64encode(b"\x04" + b"x" * 64).decode().rstrip("=")
        response = self.client.post("/api/push/subscriptions/", payload, format="json")
        self.assertEqual(response.status_code, 400)

    def test_deactivating_device_disables_only_push_for_that_device(self):
        device = PushSubscription.objects.create(user=self.user, **self.payload("https://fcm.googleapis.com/one"))
        self.client.patch(f"/api/push/subscriptions/{device.pk}/", {"active": False}, format="json")
        device.refresh_from_db()
        self.assertFalse(device.active)
        self.assertEqual(self.client.get("/api/notifications/").status_code, 200)
        self.assertEqual(PushSubscription.objects.filter(user=self.user).count(), 1)

    @override_settings(**_TEST_VAPID_SETTINGS)
    def test_public_key_endpoint_returns_only_a_valid_public_key(self):
        response = self.client.get("/api/push/public-key/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"public_key": _TEST_PUBLIC_KEY})
        self.assertNotIn(_TEST_PRIVATE_KEY_ENCODED, str(response.json()))


class PushDeliveryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("push-delivery", password="password123")
        self.device = PushSubscription.objects.create(
            user=self.user,
            device_name="Chrome",
            endpoint="https://fcm.googleapis.com/device",
            p256dh="p256dh",
            auth="auth",
        )

    @override_settings(**_TEST_VAPID_SETTINGS)
    def test_successful_delivery_updates_last_successful_timestamp(self):
        with mock.patch("pywebpush.webpush") as webpush:
            send_push_to_user(self.user.pk, "RESERVATION", "/reservations/1", "reservation:1:approved")
        self.device.refresh_from_db()
        self.assertEqual(webpush.call_count, 1)
        self.assertIsNotNone(self.device.last_successful_delivery)
        payload = webpush.call_args.kwargs["data"]
        content = json.loads(payload)
        self.assertIn("Sign in to view it", content["body"])
        self.assertEqual(content["url"], "/reservations/1")
        self.assertNotIn("event_name", content)

    @override_settings(**_TEST_VAPID_SETTINGS)
    def test_expired_subscription_is_removed(self):
        from pywebpush import WebPushException

        gone = WebPushException("expired", response=mock.Mock(status_code=410))
        with mock.patch("pywebpush.webpush", side_effect=gone):
            send_push_to_user(self.user.pk, "RESERVATION", "/notifications")
        self.assertFalse(PushSubscription.objects.filter(pk=self.device.pk).exists())

    def test_duplicate_event_key_creates_only_one_in_app_notification(self):
        with self.captureOnCommitCallbacks(execute=True):
            first = notify(self.user, "RESERVATION", "Approved", event_key="reservation:1:approved")
            again = notify(self.user, "RESERVATION", "Approved", event_key="reservation:1:approved")
        self.assertEqual(first.pk, again.pk)
        self.assertEqual(Notification.objects.filter(user=self.user).count(), 1)

    def test_staff_event_does_not_notify_requesters(self):
        admin = User.objects.create_user("push-admin", password="password123", role=User.Role.ADMIN)
        staff = User.objects.create_user("push-staff", password="password123", role=User.Role.STAFF)
        requester = User.objects.create_user("push-requester", password="password123", role=User.Role.REQUESTER)
        with self.captureOnCommitCallbacks(execute=True):
            notify_staff("RESERVATION", "New reservation", event_key="reservation:99:submitted")
        self.assertTrue(Notification.objects.filter(user=admin).exists())
        self.assertTrue(Notification.objects.filter(user=staff).exists())
        self.assertFalse(Notification.objects.filter(user=requester).exists())

    @override_settings(**_TEST_VAPID_SETTINGS)
    def test_one_failed_device_does_not_block_other_devices(self):
        second = PushSubscription.objects.create(
            user=self.user,
            device_name="Edge",
            endpoint="https://fcm.googleapis.com/device-2",
            p256dh="p256dh-2",
            auth="auth-2",
        )
        with mock.patch("pywebpush.webpush", side_effect=[RuntimeError("offline"), mock.DEFAULT]) as webpush:
            send_push_to_user(self.user.pk, "RESERVATION", "/notifications")
        self.assertEqual(webpush.call_count, 2)
        self.device.refresh_from_db()
        second.refresh_from_db()
        self.assertIsNotNone(self.device.last_successful_delivery)
        self.assertIsNone(second.last_successful_delivery)

    @override_settings(**_TEST_VAPID_SETTINGS)
    def test_expired_admin_device_does_not_block_other_staff_recipients(self):
        admin = User.objects.create_user("delivery-admin", password="password123", role=User.Role.ADMIN)
        staff = User.objects.create_user("delivery-staff", password="password123", role=User.Role.STAFF)
        expired_device = PushSubscription.objects.create(
            user=admin,
            endpoint="https://fcm.googleapis.com/admin-device",
            p256dh="p256dh-admin",
            auth="auth-admin",
        )
        live_device = PushSubscription.objects.create(
            user=staff,
            endpoint="https://fcm.googleapis.com/staff-device",
            p256dh="p256dh-staff",
            auth="auth-staff",
        )
        from pywebpush import WebPushException

        expired = WebPushException("expired", response=mock.Mock(status_code=410))
        with mock.patch("pywebpush.webpush", side_effect=[expired, mock.DEFAULT]) as webpush:
            with self.captureOnCommitCallbacks(execute=True):
                notify_staff("RESERVATION", "New reservation", event_key="reservation:123:submitted")

        self.assertFalse(PushSubscription.objects.filter(pk=expired_device.pk).exists())
        live_device.refresh_from_db()
        self.assertTrue(live_device.active)
        self.assertIsNotNone(live_device.last_successful_delivery)
        self.assertEqual(webpush.call_count, 2)

    @override_settings(**_TEST_VAPID_SETTINGS)
    def test_mismatched_vapid_keys_skip_delivery_without_raising(self):
        with mock.patch("pywebpush.webpush") as webpush:
            with override_settings(VAPID_PUBLIC_KEY="A" * 87):
                send_push_to_user(self.user.pk, "RESERVATION", "/notifications")
        webpush.assert_not_called()

    @override_settings(**_TEST_VAPID_SETTINGS)
    def test_inactive_device_is_not_sent_push(self):
        self.device.active = False
        self.device.save(update_fields=["active"])
        with mock.patch("pywebpush.webpush") as webpush:
            send_push_to_user(self.user.pk, "RESERVATION", "/notifications")
        webpush.assert_not_called()
