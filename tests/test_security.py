"""Tests for security headers, rate limiting, and audit logging."""

from __future__ import annotations

import json
import logging
import os
import sys
import unittest
from io import StringIO
from unittest.mock import patch

from fastapi.testclient import TestClient

TEST_JWT_SECRET = "test-jwt-secret-for-security-tests"
TEST_ADMIN_PASSWORD = "test-admin-password"


class TestSecurityMiddleware(unittest.TestCase):
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

    def test_security_headers_on_health(self) -> None:
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(res.headers.get("X-Frame-Options"), "DENY")
        self.assertIn("Content-Security-Policy", res.headers)
        self.assertEqual(res.headers.get("Referrer-Policy"), "strict-origin-when-cross-origin")

    def test_security_headers_relaxed_for_docs(self) -> None:
        res = self.client.get("/docs")
        self.assertEqual(res.status_code, 200)
        csp = res.headers.get("Content-Security-Policy", "")
        self.assertIn("cdn.jsdelivr.net", csp)


class TestRateLimiting(unittest.TestCase):
    def test_rate_limit_returns_429(self) -> None:
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET": TEST_JWT_SECRET,
                "ADMIN_PASSWORD": TEST_ADMIN_PASSWORD,
                "RATE_LIMIT_ENABLED": "true",
            },
            clear=False,
        ):
            with (
                patch("dotenv.load_dotenv"),
                patch("services.database.init_db"),
                patch("services.database.ping_database", return_value=True),
                patch("services.audit_log.configure_audit_logging"),
                patch("middleware.rate_limit.ENDPOINT_RULES", {"/auth/login": (2, 60)}),
            ):
                sys.modules.pop("app", None)
                from app import app

                client = TestClient(app)
                for _ in range(2):
                    res = client.post(
                        "/auth/login",
                        json={"role": "admin", "password": "wrong-password"},
                    )
                    self.assertIn(res.status_code, (401, 503))

                res = client.post(
                    "/auth/login",
                    json={"role": "admin", "password": "wrong-password"},
                )
                self.assertEqual(res.status_code, 429)
                self.assertEqual(res.json()["detail"], "Too many requests. Please try again later.")
                sys.modules.pop("app", None)


class TestAuditLogging(unittest.TestCase):
    def test_login_failure_emits_audit_event(self) -> None:
        log_buffer = StringIO()
        handler = logging.StreamHandler(log_buffer)
        handler.setFormatter(logging.Formatter("%(message)s"))

        audit_logger = logging.getLogger("audit")
        audit_logger.handlers.clear()
        audit_logger.addHandler(handler)
        audit_logger.setLevel(logging.INFO)
        audit_logger.propagate = False

        with patch.dict(
            os.environ,
            {
                "JWT_SECRET": TEST_JWT_SECRET,
                "ADMIN_PASSWORD": TEST_ADMIN_PASSWORD,
                "RATE_LIMIT_ENABLED": "false",
            },
            clear=False,
        ):
            with (
                patch("dotenv.load_dotenv"),
                patch("services.database.init_db"),
                patch("services.database.ping_database", return_value=True),
            ):
                import services.audit_log as audit_log_module

                audit_log_module._audit_logger = audit_logger

                sys.modules.pop("app", None)
                from app import app

                client = TestClient(app)
                res = client.post(
                    "/auth/login",
                    json={"role": "admin", "password": "wrong-password"},
                )
                self.assertEqual(res.status_code, 401)

                output = log_buffer.getvalue().strip()
                self.assertTrue(output)
                event = json.loads(output.splitlines()[-1])
                self.assertEqual(event["event"], "auth.login.failure")
                self.assertEqual(event["status"], "failure")
                self.assertEqual(event["role"], "admin")

                audit_logger.handlers.clear()
                sys.modules.pop("app", None)


if __name__ == "__main__":
    unittest.main()
