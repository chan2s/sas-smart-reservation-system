"""Account deactivation / reactivation tests.

Covers the acceptance criteria for administrator-managed account status:

* an administrator can deactivate an active account and reactivate it later;
* the list reports the status and can filter on it (with search, role, and
  pagination);
* a deactivated account cannot sign in with email/password or through Google,
  and Google sign-in never reactivates it;
* tokens issued before deactivation stop working (access and refresh);
* non-administrators are refused, and self / superuser / last-superuser
  safeguards hold;
* nothing is deleted or reset: role, password, organization, reservations,
  social link, and login history all survive.
"""

from datetime import date, time
from unittest import mock
from urllib.parse import parse_qs, urlparse

from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from facilities.models import Facility
from reservations.models import Reservation

from .models import AuditLog, LoginActivity, User

PASSWORD = "pass1234!"
STATUS_URL = "/api/auth/users/{pk}/status/"
USERS_URL = "/api/auth/users/"
LOGIN_URL = "/api/auth/login/"
ME_URL = "/api/auth/me/"
REFRESH_URL = "/api/auth/refresh/"


def _client_as(user) -> APIClient:
    """Authenticated client without going through /login/ (no throttle/record)."""
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _set_status(client, user, is_active: bool):
    return client.post(
        STATUS_URL.format(pk=user.pk), {"is_active": is_active}, format="json"
    )


def _make_reservation(requester) -> Reservation:
    facility = Facility.objects.create(
        name="Gymnasium",
        facility_type=Facility.FacilityType.GYMNASIUM,
        capacity=100,
        location="Main Building",
    )
    return Reservation.objects.create(
        requester=requester,
        event_name="Founders Day",
        facility=facility,
        date=date(2026, 9, 14),
        start_time=time(9, 0),
        end_time=time(11, 0),
    )


def _oauth_callback(client, email: str):
    """Drive the real Google callback through a mocked identity exchange."""
    userinfo = {
        "sub": f"google-sub-{email}",
        "email": email,
        "email_verified": True,
        "given_name": "Juan",
        "family_name": "Dela Cruz",
    }
    with override_settings(GOOGLE_CLIENT_ID="test-id", GOOGLE_CLIENT_SECRET="test-secret"):
        with mock.patch("accounts.oauth_views.requests.post") as mock_post, mock.patch(
            "accounts.oauth_views.requests.get"
        ) as mock_get:
            mock_post.return_value.status_code = 200
            mock_post.return_value.raise_for_status.return_value = None
            mock_post.return_value.json.return_value = {"access_token": "g-token"}
            mock_get.return_value.status_code = 200
            mock_get.return_value.raise_for_status.return_value = None
            mock_get.return_value.json.return_value = userinfo
            start_url = client.get("/api/auth/google/start/").data["authorize_url"]
            state = parse_qs(urlparse(start_url).query)["state"][0]
            return client.get(
                "/api/auth/google/callback/", {"code": "auth-code", "state": state}
            )


class _BaseManagementTest(APITestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user(
            username="admin", password=PASSWORD, role=User.Role.ADMIN
        )
        self.superuser = User.objects.create_superuser(
            username="root", password=PASSWORD, email="root@school.edu"
        )
        self.requester = User.objects.create_user(
            username="req",
            password=PASSWORD,
            email="req@school.edu",
            role=User.Role.REQUESTER,
        )
        self.admin_client = _client_as(self.admin)

    def tearDown(self):
        cache.clear()


class DeactivationEndpointTests(_BaseManagementTest):
    def test_admin_deactivates_an_active_user(self):
        response = _set_status(self.admin_client, self.requester, False)
        self.assertEqual(response.status_code, 200)
        self.requester.refresh_from_db()
        self.assertFalse(self.requester.is_active)
        # The response reports the updated account status.
        self.assertEqual(response.data["user"]["id"], self.requester.pk)
        self.assertFalse(response.data["user"]["is_active"])
        self.assertIn("deactivated", response.data["detail"].lower())

    def test_deactivation_is_audited(self):
        _set_status(self.admin_client, self.requester, False)
        entry = AuditLog.objects.filter(
            action=AuditLog.Action.USER_DEACTIVATED, actor=self.admin
        ).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.object_id, str(self.requester.pk))

    def test_admin_reactivates_an_inactive_user(self):
        self.requester.is_active = False
        self.requester.save(update_fields=["is_active"])
        response = _set_status(self.admin_client, self.requester, True)
        self.assertEqual(response.status_code, 200)
        self.requester.refresh_from_db()
        self.assertTrue(self.requester.is_active)
        self.assertTrue(response.data["user"]["is_active"])
        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditLog.Action.USER_REACTIVATED, actor=self.admin
            ).exists()
        )

    def test_repeating_the_same_status_is_an_idempotent_no_op(self):
        _set_status(self.admin_client, self.requester, False)
        again = _set_status(self.admin_client, self.requester, False)
        self.assertEqual(again.status_code, 200)
        self.assertFalse(again.data["user"]["is_active"])
        # Nothing changed the second time, so nothing extra was audited.
        self.assertEqual(
            AuditLog.objects.filter(action=AuditLog.Action.USER_DEACTIVATED).count(), 1
        )

    def test_invalid_payload_is_rejected(self):
        for payload in ({}, {"is_active": "maybe"}, {"is_active": None}):
            with self.subTest(payload=payload):
                response = self.admin_client.post(
                    STATUS_URL.format(pk=self.requester.pk), payload, format="json"
                )
                self.assertEqual(response.status_code, 400)
        self.requester.refresh_from_db()
        self.assertTrue(self.requester.is_active)

    def test_missing_account_returns_404(self):
        for payload in (True, False):
            with self.subTest(is_active=payload):
                response = self.admin_client.post(
                    "/api/auth/users/999999/status/",
                    {"is_active": payload},
                    format="json",
                )
                self.assertEqual(response.status_code, 404)

    def test_get_is_not_allowed(self):
        self.assertEqual(
            self.admin_client.get(STATUS_URL.format(pk=self.requester.pk)).status_code,
            405,
        )


class DeactivationGuardTests(_BaseManagementTest):
    def test_admin_cannot_deactivate_own_account(self):
        response = _set_status(self.admin_client, self.admin, False)
        self.assertEqual(response.status_code, 400)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_protected_superuser_cannot_be_deactivated(self):
        """Only one active superuser exists — the last-superuser guard fires."""
        response = _set_status(self.admin_client, self.superuser, False)
        self.assertEqual(response.status_code, 400)
        self.assertIn("last active superuser", response.data["detail"].lower())
        self.superuser.refresh_from_db()
        self.assertTrue(self.superuser.is_active)

    def test_superuser_stays_protected_when_others_exist(self):
        """A superuser is a protected system account, not just the last one."""
        User.objects.create_superuser(
            username="root2", password=PASSWORD, email="root2@school.edu"
        )
        response = _set_status(self.admin_client, self.superuser, False)
        self.assertEqual(response.status_code, 400)
        self.assertIn("protected system account", response.data["detail"].lower())
        self.superuser.refresh_from_db()
        self.assertTrue(self.superuser.is_active)

    def test_staff_cannot_change_status(self):
        staff = User.objects.create_user(
            username="staff", password=PASSWORD, role=User.Role.STAFF
        )
        client = _client_as(staff)
        self.assertEqual(_set_status(client, self.requester, False).status_code, 403)
        self.assertEqual(_set_status(client, self.requester, True).status_code, 403)
        self.requester.refresh_from_db()
        self.assertTrue(self.requester.is_active)

    def test_requester_cannot_change_status(self):
        self.requester.is_active = False
        self.requester.save(update_fields=["is_active"])
        client = _client_as(User.objects.create_user(username="other"))
        self.assertEqual(_set_status(client, self.requester, True).status_code, 403)
        self.requester.refresh_from_db()
        self.assertFalse(self.requester.is_active)

    def test_anonymous_cannot_change_status(self):
        response = APIClient().post(
            STATUS_URL.format(pk=self.requester.pk), {"is_active": False}, format="json"
        )
        self.assertEqual(response.status_code, 401)
        self.requester.refresh_from_db()
        self.assertTrue(self.requester.is_active)


class DeactivatedAccountAccessTests(_BaseManagementTest):
    def test_inactive_user_cannot_log_in_with_password(self):
        self.requester.is_active = False
        self.requester.save(update_fields=["is_active"])
        response = APIClient().post(
            LOGIN_URL, {"username": "req", "password": PASSWORD}
        )
        self.assertIn(response.status_code, (400, 401))
        self.assertNotIn("access", response.data)
        # No session artifact is written for a refused sign-in.
        self.assertEqual(LoginActivity.objects.filter(user=self.requester).count(), 0)

    def test_existing_access_token_stops_working_after_deactivation(self):
        login = APIClient().post(LOGIN_URL, {"username": "req", "password": PASSWORD})
        self.assertEqual(login.status_code, 200)
        access = login.data["access"]

        _set_status(self.admin_client, self.requester, False)

        authed = APIClient()
        authed.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertEqual(authed.get(ME_URL).status_code, 401)

    def test_existing_refresh_token_is_refused_after_deactivation(self):
        login = APIClient().post(LOGIN_URL, {"username": "req", "password": PASSWORD})
        refresh = login.data["refresh"]

        _set_status(self.admin_client, self.requester, False)

        response = APIClient().post(REFRESH_URL, {"refresh": refresh}, format="json")
        self.assertEqual(response.status_code, 401)

    def test_reactivated_user_can_log_in_again(self):
        login = APIClient().post(LOGIN_URL, {"username": "req", "password": PASSWORD})
        self.assertEqual(login.status_code, 200)

        _set_status(self.admin_client, self.requester, False)
        self.assertEqual(
            APIClient().post(LOGIN_URL, {"username": "req", "password": PASSWORD}).status_code,
            401,
        )

        _set_status(self.admin_client, self.requester, True)
        again = APIClient().post(LOGIN_URL, {"username": "req", "password": PASSWORD})
        self.assertEqual(again.status_code, 200)
        self.assertIn("access", again.data)

    def test_deactivated_google_account_cannot_sign_in_and_is_not_reactivated(self):
        email = "deactivated@gmail.com"
        first = _oauth_callback(APIClient(), email)
        self.assertEqual(first.status_code, 302)
        self.assertIn("access=", first.url)
        user = User.objects.get(email=email)
        self.assertEqual(LoginActivity.objects.filter(user=user).count(), 1)

        self.assertEqual(_set_status(self.admin_client, user, False).status_code, 200)

        again = _oauth_callback(APIClient(), email)
        self.assertEqual(again.status_code, 302)
        self.assertIn("google_error=account_deactivated", again.url)
        self.assertNotIn("access=", again.url)

        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertEqual(User.objects.filter(email=email).count(), 1)
        # A refused attempt is not a sign-in.
        self.assertEqual(LoginActivity.objects.filter(user=user).count(), 1)

    def test_reactivated_google_account_regains_access(self):
        from allauth.socialaccount.models import SocialAccount

        email = "google-back@gmail.com"
        _oauth_callback(APIClient(), email)
        user = User.objects.get(email=email)

        _set_status(self.admin_client, user, False)
        self.assertEqual(_set_status(self.admin_client, user, True).status_code, 200)

        third = _oauth_callback(APIClient(), email)
        self.assertEqual(third.status_code, 302)
        self.assertIn("access=", third.url)
        self.assertTrue(SocialAccount.objects.filter(user=user).exists())


class DeactivationPreservesDataTests(_BaseManagementTest):
    def test_deactivation_keeps_profile_role_and_credentials(self):
        from allauth.socialaccount.models import SocialAccount

        self.requester.affiliation = User.Affiliation.NORSU_FACULTY_STAFF
        self.requester.organization = "College of Engineering"
        self.requester.save()
        password_hash = self.requester.password
        SocialAccount.objects.create(
            user=self.requester,
            provider="google",
            uid="google-sub-keep",
            extra_data={"email": "req@school.edu"},
        )

        _set_status(self.admin_client, self.requester, False)
        _set_status(self.admin_client, self.requester, True)

        self.requester.refresh_from_db()
        self.assertEqual(self.requester.role, User.Role.REQUESTER)
        self.assertEqual(
            self.requester.affiliation, User.Affiliation.NORSU_FACULTY_STAFF
        )
        self.assertEqual(self.requester.organization, "College of Engineering")
        self.assertEqual(self.requester.password, password_hash)
        self.assertTrue(self.requester.has_usable_password())
        self.assertTrue(SocialAccount.objects.filter(user=self.requester).exists())

    def test_deactivation_keeps_reservations_and_login_history(self):
        reservation = _make_reservation(self.requester)
        APIClient().post(LOGIN_URL, {"username": "req", "password": PASSWORD})
        history = LoginActivity.objects.filter(user=self.requester).count()
        self.assertEqual(history, 1)

        _set_status(self.admin_client, self.requester, False)

        reservation.refresh_from_db()
        self.assertEqual(reservation.requester_id, self.requester.pk)
        self.assertEqual(LoginActivity.objects.filter(user=self.requester).count(), 1)
        self.assertTrue(User.objects.filter(pk=self.requester.pk).exists())

    def test_deactivated_account_can_still_be_deleted(self):
        _set_status(self.admin_client, self.requester, False)
        response = self.admin_client.delete(f"/api/auth/users/{self.requester.pk}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(User.objects.filter(pk=self.requester.pk).exists())


class UserListStatusTests(_BaseManagementTest):
    def setUp(self):
        super().setUp()
        self.inactive = User.objects.create_user(
            username="gone", email="gone@school.edu", is_active=False
        )
        self.staff = User.objects.create_user(
            username="staff", email="staff@school.edu", role=User.Role.STAFF
        )

    def _rows(self, response):
        return {row["username"]: row for row in response.data["results"]}

    def test_list_reports_each_account_status(self):
        rows = self._rows(self.admin_client.get(USERS_URL))
        self.assertTrue(rows["req"]["is_active"])
        self.assertFalse(rows["gone"]["is_active"])

    def test_status_filter_returns_only_matching_accounts(self):
        inactive = self.admin_client.get(f"{USERS_URL}?is_active=false")
        self.assertEqual({r["username"] for r in inactive.data["results"]}, {"gone"})

        active = self.admin_client.get(f"{USERS_URL}?is_active=true")
        usernames = {r["username"] for r in active.data["results"]}
        self.assertIn("req", usernames)
        self.assertNotIn("gone", usernames)

    def test_status_filter_combines_with_search_and_role(self):
        response = self.admin_client.get(
            f"{USERS_URL}?is_active=true&role=STAFF&search=staff"
        )
        self.assertEqual({r["username"] for r in response.data["results"]}, {"staff"})

        empty = self.admin_client.get(f"{USERS_URL}?is_active=false&role=STAFF")
        self.assertEqual(empty.data["count"], 0)

    def test_status_filter_is_paginated(self):
        User.objects.bulk_create(
            User(username=f"gone{n}", is_active=False) for n in range(25)
        )
        response = self.admin_client.get(f"{USERS_URL}?is_active=false")
        self.assertEqual(response.data["count"], 26)
        self.assertEqual(len(response.data["results"]), 20)
        second = self.admin_client.get(f"{USERS_URL}?is_active=false&page=2")
        self.assertEqual(len(second.data["results"]), 6)
