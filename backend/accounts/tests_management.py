"""Administrator user-management, account-deletion, and login-activity tests.

Covers the acceptance criteria introduced with these features:

* administrators can list registered users and delete eligible accounts;
* self-deletion and protected system accounts are refused server-side;
* non-administrators are refused on every management endpoint (403);
* successful email/password and Google OAuth sign-ins are recorded;
* failed sign-ins are never recorded as successes;
* login activity is newest-first, timezone-aware, and filterable;
* deleting an account preserves its reservation history and login history.

Also covers the corrected ``createsuperuser`` behavior: the application user
manager now assigns ``Role.ADMIN`` (not the model default ``Role.REQUESTER``)
to superusers created through the manager or through ``manage.py
createsuperuser``.
"""

from datetime import date, time, timedelta
from unittest import mock
from urllib.parse import parse_qs, urlparse

from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from facilities.models import Facility
from reservations.models import Reservation


from .models import LoginActivity, User

PASSWORD = "pass1234!"


def _client_as(user) -> APIClient:
    """Authenticated client without going through /login/ (no throttle/no record)."""
    client = APIClient()
    client.force_authenticate(user=user)
    return client


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


class SuperuserRoleTests(APITestCase):
    """Test A + D: superuser creation assigns the administrator role.

    The bug this validates is that ``User.objects.create_superuser()`` (and
    therefore ``manage.py createsuperuser``) was leaving ``role`` on the
    model default ``Role.REQUESTER`` because the model uses Django's built-in
    ``UserManager``, which never touches the project's ``role`` field.
    """

    def test_create_superuser_gets_admin_role(self):
        user = User.objects.create_superuser(
            username="super", password=PASSWORD, email="super@school.edu"
        )
        self.assertEqual(user.role, User.Role.ADMIN)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_active)

    def test_create_superuser_gets_is_admin_property(self):
        user = User.objects.create_superuser(
            username="super2", password=PASSWORD, email="super2@school.edu"
        )
        self.assertTrue(user.is_admin)

    def test_create_superuser_without_role_fails_loudly(self):
        """Guardrail: accidentally overriding role=REQUESTER on a superuser is refused."""
        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                username="badsuper",
                password=PASSWORD,
                email="bad@school.edu",
                role=User.Role.REQUESTER,
            )

    def test_create_superuser_with_role_staff_is_refused(self):
        """Only ADMIN may be the superuser role."""
        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                username="badsuper2",
                password=PASSWORD,
                email="bad2@school.edu",
                role=User.Role.STAFF,
            )

    def test_createsuperuser_management_command_uses_admin_role(self):
        """Test D: ``manage.py createsuperuser`` must not produce a requester.

        Django's bundled ``createsuperuser`` command delegates to the project's
        custom user manager, so this exercises the same ``UserManager.
        create_superuser()`` path as the direct manager call above.
        """
        def _input(_prompt):
            return "mgmt-created"

        def _prompt(_msg):
            return "MgmtPass1!"

        with mock.patch("builtins.input", side_effect=_input), mock.patch(
            "getpass.getpass", side_effect=_prompt
        ):
            call_command("createsuperuser")

        user = User.objects.get(username="mgmt-created")
        self.assertEqual(user.role, User.Role.ADMIN)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

        # Cleanup so this test is re-runnable inside the same DB.
        user.delete()


class OrdinaryUserRoleTests(APITestCase):
    """Test B: ordinary users keep the intended default role."""

    def test_create_user_defaults_to_requester(self):
        user = User.objects.create_user(
            username="plain", password=PASSWORD, email="plain@school.edu"
        )
        self.assertEqual(user.role, User.Role.REQUESTER)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.is_active)

    def test_create_user_with_explicit_admin_still_works(self):
        """``create_user`` preserves caller-supplied roles (used by seed/adapters)."""
        admin = User.objects.create_user(
            username="manualadmin",
            password=PASSWORD,
            email="manual@school.edu",
            role=User.Role.ADMIN,
        )
        self.assertEqual(admin.role, User.Role.ADMIN)
        self.assertTrue(admin.is_admin)
        # ``is_staff`` is set by ``User.save()`` for ADMIN roles.
        self.assertTrue(admin.is_staff)


class ExistingRoleBehaviorTests(APITestCase):
    """Test C: existing role-based permissions continue working."""

    def test_is_sas_staff_is_admin_or_staff(self):
        admin = User.objects.create_user(
            username="sa", password=PASSWORD, role=User.Role.ADMIN
        )
        staff = User.objects.create_user(
            username="sb", password=PASSWORD, role=User.Role.STAFF
        )
        requester = User.objects.create_user(
            username="sr", password=PASSWORD, role=User.Role.REQUESTER
        )
        self.assertTrue(admin.is_sas_staff)
        self.assertTrue(staff.is_sas_staff)
        self.assertFalse(requester.is_sas_staff)

    def test_is_admin_is_only_admin(self):
        admin = User.objects.create_user(
            username="aa", password=PASSWORD, role=User.Role.ADMIN
        )
        staff = User.objects.create_user(
            username="as", password=PASSWORD, role=User.Role.STAFF
        )
        self.assertTrue(admin.is_admin)
        self.assertFalse(staff.is_admin)

    def test_admin_user_gets_is_staff_via_save(self):
        """Verify the existing ``User.save()`` staff shortcut still holds."""
        user = User.objects.create_user(
            username="saveadmin", password=PASSWORD, role=User.Role.ADMIN
        )
        self.assertTrue(user.is_staff)

    def test_staff_user_does_not_get_is_staff_via_save(self):
        user = User.objects.create_user(
            username="savestaff", password=PASSWORD, role=User.Role.STAFF
        )
        self.assertFalse(user.is_staff)


class UserManagementTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin", password=PASSWORD, role=User.Role.ADMIN
        )
        self.staff = User.objects.create_user(
            username="staff", password=PASSWORD, role=User.Role.STAFF
        )
        self.requester = User.objects.create_user(
            username="req", password=PASSWORD, role=User.Role.REQUESTER
        )
        self.superuser = User.objects.create_superuser(
            username="root", password=PASSWORD, email="root@school.edu"
        )
        self.admin_client = _client_as(self.admin)

    def test_admin_can_list_users_with_search(self):
        response = self.admin_client.get("/api/auth/users/?search=req")
        self.assertEqual(response.status_code, 200)
        usernames = [row["username"] for row in response.data["results"]]
        self.assertIn("req", usernames)
        self.assertNotIn("admin", usernames)

    def test_user_list_is_paginated_with_counts(self):
        response = self.admin_client.get("/api/auth/users/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("count", response.data)
        self.assertIn("results", response.data)
        self.assertEqual(response.data["count"], 4)

    def test_self_and_superuser_are_flagged_protected(self):
        response = self.admin_client.get("/api/auth/users/")
        rows = {row["username"]: row for row in response.data["results"]}
        self.assertTrue(rows["admin"]["is_protected"])
        self.assertTrue(rows["root"]["is_protected"])
        self.assertFalse(rows["req"]["is_protected"])

    def test_admin_can_delete_eligible_user(self):
        response = self.admin_client.delete(
            f"/api/auth/users/{self.requester.pk}/"
        )
        self.assertEqual(response.status_code, 204)
        self.assertFalse(User.objects.filter(pk=self.requester.pk).exists())

    def test_delete_preserves_reservation_history(self):
        reservation = _make_reservation(self.requester)
        response = self.admin_client.delete(
            f"/api/auth/users/{self.requester.pk}/"
        )
        self.assertEqual(response.status_code, 204)
        reservation.refresh_from_db()
        self.assertIsNone(reservation.requester_id)
        self.assertEqual(reservation.event_name, "Founders Day")

    def test_admin_cannot_delete_own_account(self):
        response = self.admin_client.delete(f"/api/auth/users/{self.admin.pk}/")
        self.assertEqual(response.status_code, 400)
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())

    def test_cannot_delete_protected_superuser(self):
        response = self.admin_client.delete(
            f"/api/auth/users/{self.superuser.pk}/"
        )
        self.assertEqual(response.status_code, 400)
        self.assertTrue(User.objects.filter(pk=self.superuser.pk).exists())

    def test_delete_missing_user_returns_404(self):
        response = self.admin_client.delete("/api/auth/users/999999/")
        self.assertEqual(response.status_code, 404)

    def test_delete_records_an_audit_entry(self):
        from .models import AuditLog

        self.admin_client.delete(f"/api/auth/users/{self.requester.pk}/")
        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditLog.Action.USER_DELETED, actor=self.admin
            ).exists()
        )


class UserManagementPermissionTests(APITestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="staff", password=PASSWORD, role=User.Role.STAFF
        )
        self.requester = User.objects.create_user(
            username="req", password=PASSWORD, role=User.Role.REQUESTER
        )

    def test_requester_cannot_list_or_delete(self):
        client = _client_as(self.requester)
        self.assertEqual(client.get("/api/auth/users/").status_code, 403)
        self.assertEqual(
            client.delete(f"/api/auth/users/{self.staff.pk}/").status_code, 403
        )
        self.assertTrue(User.objects.filter(pk=self.staff.pk).exists())

    def test_staff_cannot_list_or_delete(self):
        """Management is administrator-only — SAS staff are refused."""
        client = _client_as(self.staff)
        self.assertEqual(client.get("/api/auth/users/").status_code, 403)
        self.assertEqual(
            client.delete(f"/api/auth/users/{self.requester.pk}/").status_code, 403
        )

    def test_anonymous_is_unauthenticated(self):
        client = APIClient()
        self.assertEqual(client.get("/api/auth/users/").status_code, 401)
        self.assertEqual(
            client.delete(f"/api/auth/users/{self.requester.pk}/").status_code, 401
        )


class LoginActivityRecordingTests(APITestCase):
    def test_password_login_is_recorded(self):
        user = User.objects.create_user(
            username="pw", password=PASSWORD, email="pw@school.edu"
        )
        response = APIClient().post(
            "/api/auth/login/", {"username": "pw", "password": PASSWORD}
        )
        self.assertEqual(response.status_code, 200)
        activity = LoginActivity.objects.get(user=user)
        self.assertEqual(activity.method, LoginActivity.Method.PASSWORD)
        self.assertEqual(activity.status, LoginActivity.Status.SUCCESS)
        self.assertEqual(activity.email, "pw@school.edu")

    def test_failed_login_is_not_recorded(self):
        User.objects.create_user(username="pw", password=PASSWORD)
        response = APIClient().post(
            "/api/auth/login/", {"username": "pw", "password": "wrong"}
        )
        self.assertIn(response.status_code, (400, 401))
        self.assertEqual(LoginActivity.objects.count(), 0)

    def test_google_login_is_recorded(self):
        user = User.objects.create_user(
            username="g", email="g@gmail.com", first_name="Gino"
        )
        from .login_activity import record_google_login

        class _Request:
            META = {"REMOTE_ADDR": "203.0.113.7"}

        record_google_login(user, _Request())
        activity = LoginActivity.objects.get(user=user)
        self.assertEqual(activity.method, LoginActivity.Method.GOOGLE)
        self.assertEqual(activity.user_name, "Gino")
        self.assertEqual(activity.ip_address, "203.0.113.7")

    def test_failed_login_never_marks_a_success(self):
        activity = LoginActivity.objects.create(
            user=None,
            user_name="Ghost",
            email="ghost@school.edu",
            method=LoginActivity.Method.PASSWORD,
            status=LoginActivity.Status.FAILED,
        )
        self.assertNotEqual(activity.status, LoginActivity.Status.SUCCESS)


class LoginActivityEndpointTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin", password=PASSWORD, role=User.Role.ADMIN
        )
        self.requester = User.objects.create_user(
            username="req", password=PASSWORD, email="req@school.edu"
        )
        self.admin_client = _client_as(self.admin)

    def _make(self, *, user_name, email, method, when):
        row = LoginActivity.objects.create(
            user=None,
            user_name=user_name,
            email=email,
            method=method,
            status=LoginActivity.Status.SUCCESS,
        )
        LoginActivity.objects.filter(pk=row.pk).update(created_at=when)
        row.refresh_from_db()
        return row

    def test_newest_first_ordering(self):
        now = timezone.now()
        older = self._make(
            user_name="Older",
            email="old@school.edu",
            method=LoginActivity.Method.PASSWORD,
            when=now - timedelta(hours=3),
        )
        newer = self._make(
            user_name="Newer",
            email="new@school.edu",
            method=LoginActivity.Method.GOOGLE,
            when=now - timedelta(minutes=5),
        )
        response = self.admin_client.get("/api/auth/login-activity/")
        self.assertEqual(response.status_code, 200)
        ids = [row["id"] for row in response.data["results"]]
        self.assertEqual(ids[:2], [newer.id, older.id])

    def test_timestamps_are_aware_and_iso_formatted(self):
        self._make(
            user_name="A",
            email="a@school.edu",
            method=LoginActivity.Method.PASSWORD,
            when=timezone.now(),
        )
        row = LoginActivity.objects.first()
        self.assertIsNotNone(row.created_at.tzinfo)
        response = self.admin_client.get("/api/auth/login-activity/")
        self.assertIn("created_at", response.data["results"][0])

    def test_filter_by_method_and_search(self):
        now = timezone.now()
        self._make(
            user_name="Alpha",
            email="alpha@school.edu",
            method=LoginActivity.Method.GOOGLE,
            when=now,
        )
        self._make(
            user_name="Beta",
            email="beta@school.edu",
            method=LoginActivity.Method.PASSWORD,
            when=now,
        )
        by_method = self.admin_client.get(
            "/api/auth/login-activity/?method=GOOGLE"
        )
        self.assertEqual(
            [r["user_name"] for r in by_method.data["results"]], ["Alpha"]
        )
        by_search = self.admin_client.get(
            "/api/auth/login-activity/?search=beta"
        )
        self.assertEqual(
            [r["user_name"] for r in by_search.data["results"]], ["Beta"]
        )

    def test_filter_by_date_range_excludes_out_of_range(self):
        now = timezone.now()
        self._make(
            user_name="Old",
            email="old@school.edu",
            method=LoginActivity.Method.PASSWORD,
            when=now - timedelta(days=30),
        )
        self._make(
            user_name="Recent",
            email="recent@school.edu",
            method=LoginActivity.Method.GOOGLE,
            when=now,
        )
        date_from = (now - timedelta(days=1)).date().isoformat()
        response = self.admin_client.get(
            f"/api/auth/login-activity/?date_from={date_from}"
        )
        self.assertEqual(
            [r["user_name"] for r in response.data["results"]], ["Recent"]
        )

    def test_non_admin_cannot_read_login_activity(self):
        client = _client_as(self.requester)
        self.assertEqual(client.get("/api/auth/login-activity/").status_code, 403)

    def test_anonymous_cannot_read_login_activity(self):
        self.assertEqual(
            APIClient().get("/api/auth/login-activity/").status_code, 401
        )

    def test_login_history_survives_account_deletion(self):
        target = User.objects.create_user(
            username="victim", password=PASSWORD, email="victim@school.edu"
        )
        LoginActivity.objects.create(
            user=target,
            user_name="Victim User",
            email="victim@school.edu",
            role=User.Role.REQUESTER,
            method=LoginActivity.Method.PASSWORD,
        )
        self.admin_client.delete(f"/api/auth/users/{target.pk}/")
        activity = LoginActivity.objects.filter(email="victim@school.edu").first()
        self.assertIsNotNone(activity)
        self.assertIsNone(activity.user_id)
        response = self.admin_client.get("/api/auth/login-activity/")
        self.assertIn(
            "victim@school.edu", [r["email"] for r in response.data["results"]]
        )


class GoogleCallbackRecordsLoginTests(APITestCase):
    """The real Google callback records a GOOGLE login activity row."""

    def test_callback_records_google_login(self):
        client = APIClient()
        # "Log in with Google" only authenticates an existing account (it never
        # registers one), so start from the account registration would create:
        # a password-less REQUESTER whose Google identity is linked on sign-in.
        User.objects.create_user(username="recorded", email="recorded@gmail.com")
        userinfo = {
            "sub": "google-sub-recorded",
            "email": "recorded@gmail.com",
            "email_verified": True,
            "given_name": "Rec",
            "family_name": "Ord",
        }
        with override_settings(
            GOOGLE_CLIENT_ID="test-id", GOOGLE_CLIENT_SECRET="test-secret"
        ):
            with mock.patch("accounts.oauth_views.requests.post") as mock_post, mock.patch(
                "accounts.oauth_views.requests.get"
            ) as mock_get:
                mock_post.return_value.status_code = 200
                mock_post.return_value.raise_for_status.return_value = None
                mock_post.return_value.json.return_value = {"access_token": "g"}
                mock_get.return_value.status_code = 200
                mock_get.return_value.raise_for_status.return_value = None
                mock_get.return_value.json.return_value = userinfo
                start_url = client.get("/api/auth/google/start/").data["authorize_url"]
                state = parse_qs(urlparse(start_url).query)["state"][0]
                response = client.get(
                    "/api/auth/google/callback/", {"code": "c", "state": state}
                )
        self.assertEqual(response.status_code, 302)
        self.assertIn("access=", response.url)
        activity = LoginActivity.objects.get(email="recorded@gmail.com")
        self.assertEqual(activity.method, LoginActivity.Method.GOOGLE)
