"""JWT admin route protection (HTTP layer).

FastAPI TestClient checks which admin routes require Bearer tokens, login flow,
and role separation (client token cannot mutate admin resources).
See TEST_GUIDE.md § Security, auth, API contract.
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

TEST_JWT_SECRET = "test-jwt-secret-for-auth-api-tests"
TEST_ADMIN_PASSWORD = "test-admin-password"


class TestAdminRouteAuth(unittest.TestCase):
    """Admin mutating routes are protected; some admin GETs remain public."""

    _env_patch: patch

    @classmethod
    def setUpClass(cls) -> None:
        cls._env_patch = patch.dict(
            os.environ,
            {
                "JWT_SECRET": TEST_JWT_SECRET,
                "ADMIN_PASSWORD": TEST_ADMIN_PASSWORD,
                "RATE_LIMIT_ENABLED": "false",
            },
            clear=False,
        )
        cls._env_patch.start()
        with (
            patch("dotenv.load_dotenv"),
            patch("services.database.init_db"),
            patch("services.database.ping_database", return_value=True),
            patch("services.audit_log.configure_audit_logging"),
        ):
            sys.modules.pop("app", None)
            from app import app

            cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._env_patch.stop()
        sys.modules.pop("app", None)

    def _admin_token(self) -> str:
        from services import auth_service

        return auth_service.create_access_token("admin")

    def _admin_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._admin_token()}"}

    def test_admin_post_without_token_returns_401(self) -> None:
        """POST /admin/languages without Authorization → 401 Not authenticated."""
        res = self.client.post(
            "/admin/languages",
            json={"code": "xx", "name": "Test"},
        )
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["detail"], "Not authenticated")

    def test_admin_get_without_token_succeeds(self) -> None:
        """GET /admin/assessments is intentionally public (list summaries)."""
        with patch("routers.admin.db_service.list_assessments_summary", return_value=[]):
            res = self.client.get("/admin/assessments")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"assessments": []})

    def test_admin_get_submissions_without_token_succeeds(self) -> None:
        """GET /admin/submissions is public for operational dashboards."""
        with patch("routers.admin.db_service.list_all_submissions", return_value=[]):
            res = self.client.get("/admin/submissions")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"submissions": []})

    def test_admin_delete_without_token_returns_401(self) -> None:
        """DELETE /admin/topics/{id} requires authentication."""
        res = self.client.delete("/admin/topics/1")
        self.assertEqual(res.status_code, 401)

    def test_admin_put_without_token_returns_401(self) -> None:
        """PUT /admin/languages/{id} requires authentication."""
        res = self.client.put(
            "/admin/languages/1",
            json={"code": "xx", "name": "Test"},
        )
        self.assertEqual(res.status_code, 401)

    def test_generate_assessment_without_token_returns_401(self) -> None:
        """POST /generate-assessment is an admin-only mutating endpoint."""
        res = self.client.post(
            "/generate-assessment",
            json={
                "topic": "Python",
                "level": "beginner",
                "types": ["mcq"],
                "questions_per_type": {"mcq": 1},
            },
        )
        self.assertEqual(res.status_code, 401)

    def test_admin_mutating_route_with_invalid_token_returns_401(self) -> None:
        """Malformed JWT → 401 Invalid or expired token."""
        res = self.client.post(
            "/admin/languages",
            json={"code": "xx", "name": "Test"},
            headers={"Authorization": "Bearer not-a-valid-token"},
        )
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["detail"], "Invalid or expired token")

    def test_admin_mutating_route_with_client_token_returns_403(self) -> None:
        """Valid client role token cannot POST admin resources → 403."""
        from services import auth_service

        client_token = auth_service.create_access_token("client", client_id="participant-1")
        res = self.client.post(
            "/admin/languages",
            json={"code": "xx", "name": "Test"},
            headers={"Authorization": f"Bearer {client_token}"},
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"], "Admin access required")

    def test_admin_login_requires_jwt_secret(self) -> None:
        """Login returns 503 when JWT_SECRET is not configured."""
        with patch("services.auth_service.jwt_configured", return_value=False):
            res = self.client.post(
                "/auth/login",
                json={"role": "admin", "password": TEST_ADMIN_PASSWORD},
            )
        self.assertEqual(res.status_code, 503)
        self.assertIn("JWT_SECRET", res.json()["detail"])

    def test_admin_login_returns_token(self) -> None:
        """Successful admin login returns bearer access_token and role."""
        res = self.client.post(
            "/auth/login",
            json={"role": "admin", "password": TEST_ADMIN_PASSWORD},
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["role"], "admin")
        self.assertEqual(body["token_type"], "bearer")
        self.assertTrue(body["access_token"])

    def test_admin_get_with_valid_token_succeeds(self) -> None:
        """Authenticated admin may also call public GET admin routes."""
        with patch("routers.admin.db_service.list_assessments_summary", return_value=[]):
            res = self.client.get("/admin/assessments", headers=self._admin_headers())
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"assessments": []})


if __name__ == "__main__":
    unittest.main()
