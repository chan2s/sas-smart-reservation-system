"""Tests for the unauthenticated reachability probe used by the PWA offline layer.

The frontend must never treat ``navigator.onLine`` as proof that Django is
reachable, so it polls ``GET /api/health/``. That endpoint has to be:

* anonymous — the check runs before (and after) a session may exist;
* database-free — reachability is about the service answering, not the DB;
* GET-only and uncacheable — so a stale proxy response cannot fake a live API.
"""

from django.test import TestCase


class HealthEndpointTests(TestCase):
    def test_anonymous_request_reports_ok(self):
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_response_is_not_cached(self):
        response = self.client.get("/api/health/")
        cache_control = response.headers.get("Cache-Control", "")
        self.assertIn("no-store", cache_control)
        self.assertIn("no-cache", cache_control)

    def test_only_get_is_allowed(self):
        self.assertEqual(self.client.post("/api/health/").status_code, 405)
        self.assertEqual(self.client.put("/api/health/").status_code, 405)
        self.assertEqual(self.client.delete("/api/health/").status_code, 405)

    def test_exposes_no_application_data(self):
        body = self.client.get("/api/health/").json()
        self.assertEqual(set(body), {"status"})
