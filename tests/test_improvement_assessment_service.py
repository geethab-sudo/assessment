"""Unit tests for improvement_assessment_service (Stage 5)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from services.improvement_assessment_service import (
    DEFAULT_QUESTIONS_REQUESTED,
    _allocate_per_topic_config,
    create_weak_areas_assessment,
)


class TestAllocatePerTopicConfig(unittest.TestCase):
    def test_splits_evenly_across_topics(self) -> None:
        cfg = _allocate_per_topic_config(["A", "B", "C"], 15)
        self.assertEqual(sum(sum(t.values()) for t in cfg.values()), 15)
        self.assertEqual(set(cfg.keys()), {"A", "B", "C"})


class TestCreateWeakAreasAssessment(unittest.TestCase):
    @patch("services.improvement_assessment_service._persist_bank_only_assessment")
    @patch("services.improvement_assessment_service._build_bank_only_rows")
    @patch(
        "services.improvement_assessment_service.employee_profile_service.get_employee_profile"
    )
    def test_creates_bank_only_assessment(
        self,
        mock_profile: unittest.mock.MagicMock,
        mock_build: unittest.mock.MagicMock,
        mock_persist: unittest.mock.MagicMock,
    ) -> None:
        mock_profile.return_value = {
            "assessments_analyzed": 3,
            "weakest_topics": ["Exception Handling"],
            "topic_performance": [
                {
                    "topic_name": "Exception Handling",
                    "last_difficulty": "beginner",
                    "average_percent": 45.0,
                }
            ],
        }
        mock_build.return_value = (
            [{"question_id": "1", "difficulty": "beginner", "bank_question_id": 1}],
            0,
        )
        mock_persist.return_value = "ASM-IMPROVE-1"

        result = create_weak_areas_assessment("E1001", "python")

        self.assertEqual(result["assessment_id"], "ASM-IMPROVE-1")
        self.assertEqual(result["questions_delivered"], 1)
        self.assertEqual(result["questions_requested"], DEFAULT_QUESTIONS_REQUESTED)
        self.assertIn("Exception Handling", result["topic_summary"] or "")
        mock_persist.assert_called_once()
        mock_build.assert_called_once()

    @patch("services.improvement_assessment_service._persist_bank_only_assessment")
    @patch("services.improvement_assessment_service._build_bank_only_rows")
    @patch(
        "services.improvement_assessment_service.employee_profile_service.get_employee_profile"
    )
    def test_shortage_still_creates_assessment(
        self,
        mock_profile: unittest.mock.MagicMock,
        mock_build: unittest.mock.MagicMock,
        mock_persist: unittest.mock.MagicMock,
    ) -> None:
        mock_profile.return_value = {
            "assessments_analyzed": 2,
            "weakest_topics": ["OOP Basics"],
            "topic_performance": [
                {
                    "topic_name": "OOP Basics",
                    "last_difficulty": "beginner",
                    "average_percent": 50.0,
                }
            ],
        }
        rows = [{"question_id": str(i), "difficulty": "beginner"} for i in range(12)]
        mock_build.return_value = (rows, 3)
        mock_persist.return_value = "ASM-SHORT"

        result = create_weak_areas_assessment(
            "E1001", "python", questions_requested=15
        )

        self.assertEqual(result["questions_delivered"], 12)
        self.assertEqual(result["assessment_id"], "ASM-SHORT")
        self.assertIn("12", result["availability_message"] or "")
        self.assertIn("15", result["availability_message"] or "")
        mock_persist.assert_called_once()

    @patch("services.improvement_assessment_service._persist_bank_only_assessment")
    @patch("services.improvement_assessment_service._build_bank_only_rows")
    @patch(
        "services.improvement_assessment_service.employee_profile_service.get_employee_profile"
    )
    def test_all_mastered_returns_no_assessment(
        self,
        mock_profile: unittest.mock.MagicMock,
        mock_build: unittest.mock.MagicMock,
        mock_persist: unittest.mock.MagicMock,
    ) -> None:
        mock_profile.return_value = {
            "assessments_analyzed": 1,
            "weakest_topics": ["OOP Basics"],
            "topic_performance": [
                {
                    "topic_name": "OOP Basics",
                    "last_difficulty": "beginner",
                    "average_percent": 40.0,
                }
            ],
        }
        mock_build.return_value = ([], 15)

        result = create_weak_areas_assessment("E1001", "python")

        self.assertIsNone(result["assessment_id"])
        self.assertEqual(result["questions_delivered"], 0)
        self.assertIn("already answered", (result["availability_message"] or "").lower())
        mock_persist.assert_not_called()

    @patch("services.llm_service.generate_questions")
    @patch("services.improvement_assessment_service._persist_bank_only_assessment")
    @patch("services.improvement_assessment_service._build_bank_only_rows")
    @patch(
        "services.improvement_assessment_service.employee_profile_service.get_employee_profile"
    )
    def test_never_calls_llm(
        self,
        mock_profile: unittest.mock.MagicMock,
        mock_build: unittest.mock.MagicMock,
        mock_persist: unittest.mock.MagicMock,
        mock_llm: unittest.mock.MagicMock,
    ) -> None:
        mock_profile.return_value = {
            "assessments_analyzed": 1,
            "weakest_topics": ["Topic A"],
            "topic_performance": [
                {
                    "topic_name": "Topic A",
                    "last_difficulty": "beginner",
                    "average_percent": 50.0,
                }
            ],
        }
        mock_build.return_value = ([{"question_id": "1"}], 0)
        mock_persist.return_value = "ASM-X"

        create_weak_areas_assessment("E1001", "python")

        mock_llm.assert_not_called()

    @patch(
        "services.improvement_assessment_service.employee_profile_service.get_employee_profile"
    )
    def test_no_history_message(self, mock_profile: unittest.mock.MagicMock) -> None:
        mock_profile.return_value = {
            "assessments_analyzed": 0,
            "weakest_topics": [],
            "topic_performance": [],
        }

        result = create_weak_areas_assessment("E1001", "python")

        self.assertIsNone(result["assessment_id"])
        self.assertIn("Complete at least one", result["availability_message"] or "")


class TestWeakAreasApi(unittest.TestCase):
    _env_patch: patch

    @classmethod
    def setUpClass(cls) -> None:
        import os
        import sys

        cls._env_patch = patch.dict(
            os.environ,
            {
                "JWT_SECRET": "test-jwt-secret",
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

            from fastapi.testclient import TestClient

            cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._env_patch.stop()
        import sys

        sys.modules.pop("app", None)

    @patch(
        "services.improvement_assessment_service.create_weak_areas_assessment",
        return_value={
            "employee_id": "E1001",
            "language_code": "python",
            "questions_requested": 15,
            "questions_delivered": 12,
            "assessment_id": "ASM-API",
            "availability_message": "You asked for **15** questions, but based on availability there are only **12** valid questions for you in our question bank.",
            "topic_summary": "Based on your last 3 assessments, we recommend extra practice on: **OOP**.",
            "weak_topics": ["OOP"],
        },
    )
    def test_post_weak_areas_endpoint(self, _mock_create: unittest.mock.MagicMock) -> None:
        resp = self.client.post(
            "/client/improvement/weak-areas",
            json={
                "employee_id": "E1001",
                "language_code": "python",
                "questions_requested": 15,
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["assessment_id"], "ASM-API")
        self.assertEqual(data["questions_delivered"], 12)


if __name__ == "__main__":
    unittest.main()
