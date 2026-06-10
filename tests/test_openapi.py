"""Verify OpenAPI schema completeness and accuracy."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

EXPECTED_ROUTES: dict[str, set[str]] = {
    "/health": {"get"},
    "/auth/login": {"post"},
    "/catalog/languages": {"get"},
    "/assessment/{assessment_id}": {"get"},
    "/assessment/{assessment_id}/report": {"get"},
    "/assessment/{assessment_id}/template": {"get"},
    "/submit-assessment": {"post"},
    "/submit-notebook-assessment": {"post"},
    "/admin/assessments": {"get"},
    "/admin/assessment/{assessment_id}": {"get"},
    "/admin/assessments/{assessment_id}": {"delete"},
    "/admin/submissions": {"get"},
    "/admin/languages": {"get", "post"},
    "/admin/languages/{language_id}": {"put"},
    "/admin/topics": {"get", "post"},
    "/admin/topics/{topic_id}": {"put", "delete"},
    "/admin/preview-questions": {"post"},
    "/admin/confirm-assessment": {"post"},
    "/admin/assessment/{assessment_id}/question/{question_id}": {"patch"},
    "/generate-assessment": {"post"},
    "/admin/question-bank": {"get"},
    "/admin/question-bank/availability": {"get"},
}


class TestOpenAPISchema(unittest.TestCase):
    _env_patch: patch
    schema: dict

    @classmethod
    def setUpClass(cls) -> None:
        cls._env_patch = patch.dict(
            os.environ,
            {
                "JWT_SECRET": "test-jwt-secret-for-openapi-tests",
                "ADMIN_PASSWORD": "test-admin-password",
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
            cls.schema = app.openapi()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._env_patch.stop()
        sys.modules.pop("app", None)

    def test_all_routes_documented(self) -> None:
        paths = self.schema.get("paths", {})
        for path, methods in EXPECTED_ROUTES.items():
            self.assertIn(path, paths, f"Missing OpenAPI path: {path}")
            documented = set(paths[path].keys())
            for method in methods:
                self.assertIn(
                    method,
                    documented,
                    f"Missing {method.upper()} for {path}",
                )

    def test_no_extra_undocumented_routes(self) -> None:
        paths = self.schema.get("paths", {})
        expected_paths = set(EXPECTED_ROUTES)
        for path in paths:
            self.assertIn(
                path,
                expected_paths,
                f"Unexpected route in OpenAPI (update EXPECTED_ROUTES): {path}",
            )

    def test_each_operation_has_summary_and_description(self) -> None:
        for path, ops in self.schema.get("paths", {}).items():
            for method, op in ops.items():
                if method in ("get", "post", "put", "delete", "patch"):
                    self.assertTrue(
                        op.get("summary"),
                        f"{method.upper()} {path} missing summary",
                    )
                    self.assertTrue(
                        op.get("description"),
                        f"{method.upper()} {path} missing description",
                    )

    def test_admin_mutating_routes_require_bearer_auth(self) -> None:
        paths = self.schema.get("paths", {})
        protected = {
            ("/admin/assessments/{assessment_id}", "delete"),
            ("/admin/languages", "post"),
            ("/admin/languages/{language_id}", "put"),
            ("/admin/topics", "post"),
            ("/admin/topics/{topic_id}", "put"),
            ("/admin/topics/{topic_id}", "delete"),
            ("/admin/preview-questions", "post"),
            ("/admin/confirm-assessment", "post"),
            ("/admin/assessment/{assessment_id}/question/{question_id}", "patch"),
            ("/generate-assessment", "post"),
        }
        for path, method in protected:
            op = paths[path][method]
            self.assertIn(
                "security",
                op,
                f"{method.upper()} {path} should declare Bearer security",
            )

    def test_admin_get_routes_have_no_security(self) -> None:
        paths = self.schema.get("paths", {})
        public_gets = {
            ("/admin/assessments", "get"),
            ("/admin/assessment/{assessment_id}", "get"),
            ("/admin/submissions", "get"),
            ("/admin/languages", "get"),
            ("/admin/topics", "get"),
            ("/admin/question-bank", "get"),
            ("/admin/question-bank/availability", "get"),
        }
        for path, method in public_gets:
            op = paths[path][method]
            self.assertNotIn(
                "security",
                op,
                f"{method.upper()} {path} should not require auth",
            )

    def test_public_routes_have_no_security(self) -> None:
        paths = self.schema.get("paths", {})
        public_no_auth: dict[str, set[str]] = {
            "/health": {"get"},
            "/auth/login": {"post"},
            "/catalog/languages": {"get"},
            "/assessment/{assessment_id}": {"get"},
            "/assessment/{assessment_id}/report": {"get"},
            "/assessment/{assessment_id}/template": {"get"},
            "/submit-assessment": {"post"},
            "/submit-notebook-assessment": {"post"},
        }
        for path, methods in public_no_auth.items():
            for method in methods:
                op = paths[path][method]
                self.assertNotIn(
                    "security",
                    op,
                    f"{method.upper()} {path} should not require auth",
                )

    def test_bearer_security_scheme_defined(self) -> None:
        schemes = self.schema.get("components", {}).get("securitySchemes", {})
        self.assertIn("BearerAuth", schemes)
        self.assertEqual(schemes["BearerAuth"]["type"], "http")
        self.assertEqual(schemes["BearerAuth"]["scheme"], "bearer")

    def test_error_schema_present(self) -> None:
        schemas = self.schema.get("components", {}).get("schemas", {})
        self.assertIn("ErrorDetail", schemas)
        self.assertIn("ValidationErrorItem", schemas)
        self.assertIn("ValidationErrorResponse", schemas)
        detail_items = schemas["ValidationErrorResponse"]["properties"]["detail"]["items"]
        self.assertEqual(detail_items["$ref"], "#/components/schemas/ValidationErrorItem")

    def test_swagger_ui_reachable(self) -> None:
        res = self.client.get("/docs")
        self.assertEqual(res.status_code, 200)

    def test_openapi_json_reachable(self) -> None:
        res = self.client.get("/openapi.json")
        self.assertEqual(res.status_code, 200)
        self.assertIn("paths", res.json())


if __name__ == "__main__":
    unittest.main()
