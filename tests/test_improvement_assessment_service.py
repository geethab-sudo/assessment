"""Client improvement assessments (``services.improvement_assessment_service``).

Stage 5 — **weak areas**: bank-only practice on weakest topics (last 3 assessments).
Stage 6 — **new areas**: bank-only on unexplored catalog topics (full history).
Includes HTTP smoke tests for POST /client/improvement/* endpoints.
See TEST_GUIDE.md § Client improvement flows.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from services.improvement_assessment_service import (
    DEFAULT_QUESTIONS_REQUESTED,
    _allocate_per_topic_config,
    _select_step_up_topics,
    create_difficulty_improvement_assessment,
    create_new_areas_assessment,
    create_weak_areas_assessment,
)


class TestAllocatePerTopicConfig(unittest.TestCase):
    """Fair split of question counts across selected topics."""

    def test_splits_evenly_across_topics(self) -> None:
        """15 questions across 3 topics sums to 15 with one entry per topic."""
        cfg = _allocate_per_topic_config(["A", "B", "C"], 15)
        self.assertEqual(sum(sum(t.values()) for t in cfg.values()), 15)
        self.assertEqual(set(cfg.keys()), {"A", "B", "C"})


class TestCreateWeakAreasAssessment(unittest.TestCase):
    """Stage 5 — personalized weak-topic practice from question bank only."""

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
        """Happy path: profile weak topics → bank rows → persisted assessment id."""
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
        """Partial bank availability still delivers an assessment with availability_message."""
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
        """When every candidate question is mastered, no assessment is created."""
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
        """Improvement path must never invoke LLM question generation."""
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
        """Employee with zero analyzed assessments gets a guidance message, no id."""
        mock_profile.return_value = {
            "assessments_analyzed": 0,
            "weakest_topics": [],
            "topic_performance": [],
        }

        result = create_weak_areas_assessment("E1001", "python")

        self.assertIsNone(result["assessment_id"])
        self.assertIn("Complete at least one", result["availability_message"] or "")


class TestCreateNewAreasAssessment(unittest.TestCase):
    """Stage 6 — practice on catalog topics the employee has never attempted."""

    @patch("services.improvement_assessment_service._persist_bank_only_assessment")
    @patch("services.improvement_assessment_service._build_bank_only_rows")
    @patch(
        "services.improvement_assessment_service.employee_profile_service.get_employee_profile"
    )
    def test_creates_bank_only_on_unexplored_topics(
        self,
        mock_profile: unittest.mock.MagicMock,
        mock_build: unittest.mock.MagicMock,
        mock_persist: unittest.mock.MagicMock,
    ) -> None:
        """Picks unexplored topics in learning-path order (Tier 1 / presets before Tier 2)."""
        mock_profile.return_value = {
            "assessments_analyzed": 2,
            "assessed_level": "beginner",
            "unexplored_topic_names": [
                "Tier 2 - Topic A",
                "Tier 2 - Topic B",
                "Tier 1 - Topic C",
            ],
        }
        mock_build.return_value = (
            [{"question_id": "1", "difficulty": "beginner"}],
            0,
        )
        mock_persist.return_value = "ASM-NEW-1"

        result = create_new_areas_assessment("E1001", "py", topics_count=2)

        self.assertEqual(result["assessment_id"], "ASM-NEW-1")
        self.assertEqual(len(result["selected_topics"]), 2)
        self.assertEqual(result["selected_topics"][0], "Tier 1 - Topic C")
        self.assertIn("Tier 2", result["selected_topics"][1])
        mock_profile.assert_called_once_with("E1001", language_code="py", scope="full_history")

    @patch(
        "services.improvement_assessment_service.employee_profile_service.get_employee_profile"
    )
    def test_no_unexplored_topics(self, mock_profile: unittest.mock.MagicMock) -> None:
        """Empty unexplored list → message that catalog is fully explored."""
        mock_profile.return_value = {
            "assessments_analyzed": 3,
            "unexplored_topic_names": [],
        }

        result = create_new_areas_assessment("E1001", "py")

        self.assertIsNone(result["assessment_id"])
        self.assertIn("explored all catalog", (result["availability_message"] or "").lower())

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
        """New-areas flow also delivers partial sets when bank is short."""
        mock_profile.return_value = {
            "assessments_analyzed": 1,
            "unexplored_topic_names": ["Tier 2 - New Topic"],
        }
        rows = [{"question_id": str(i)} for i in range(10)]
        mock_build.return_value = (rows, 5)
        mock_persist.return_value = "ASM-SHORT-NEW"

        result = create_new_areas_assessment("E1001", "py", questions_requested=15)

        self.assertEqual(result["questions_delivered"], 10)
        self.assertEqual(result["assessment_id"], "ASM-SHORT-NEW")
        self.assertIn("10", result["availability_message"] or "")


class TestWeakAreasApi(unittest.TestCase):
    """HTTP contract for improvement endpoints (service layer mocked)."""

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
        """POST /client/improvement/weak-areas returns 200 and response schema fields."""
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

    @patch(
        "services.improvement_assessment_service.create_new_areas_assessment",
        return_value={
            "employee_id": "E1001",
            "language_code": "py",
            "questions_requested": 15,
            "questions_delivered": 15,
            "assessment_id": "ASM-NEW-API",
            "topic_summary": "Based on your full assessment history...",
            "selected_topics": ["Tier 2 - Topic A"],
        },
    )
    def test_post_new_areas_endpoint(self, _mock_create: unittest.mock.MagicMock) -> None:
        """POST /client/improvement/new-areas returns 200 with selected_topics."""
        resp = self.client.post(
            "/client/improvement/new-areas",
            json={
                "employee_id": "E1001",
                "language_code": "py",
                "questions_requested": 15,
                "topics_count": 3,
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["assessment_id"], "ASM-NEW-API")
        self.assertEqual(data["selected_topics"], ["Tier 2 - Topic A"])

    @patch(
        "services.improvement_assessment_service.create_difficulty_improvement_assessment",
        return_value={
            "employee_id": "E1001",
            "language_code": "python",
            "questions_requested": 15,
            "questions_delivered": 10,
            "assessment_id": "ASM-DIFF-API",
            "topic_summary": "Step up summary",
            "selected_topics": ["OOP Basics"],
            "target_difficulty_by_topic": {"OOP Basics": "intermediate"},
        },
    )
    def test_post_difficulty_endpoint(self, _mock_create: unittest.mock.MagicMock) -> None:
        """POST /client/improvement/difficulty returns 200 with target difficulties."""
        resp = self.client.post(
            "/client/improvement/difficulty",
            json={
                "employee_id": "E1001",
                "language_code": "python",
                "questions_requested": 15,
                "topics_count": 3,
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["assessment_id"], "ASM-DIFF-API")
        self.assertEqual(data["target_difficulty_by_topic"]["OOP Basics"], "intermediate")


class TestSelectStepUpTopics(unittest.TestCase):
    """Step-up topic selection uses recommended vs last assessed difficulty."""

    def test_selects_topics_ready_to_step_up(self) -> None:
        perf = [
            {
                "topic_name": "OOP",
                "average_percent": 80.0,
                "last_difficulty": "beginner",
            },
            {
                "topic_name": "Weak Topic",
                "average_percent": 50.0,
                "last_difficulty": "beginner",
            },
        ]
        recommended = {"OOP": "intermediate", "Weak Topic": "beginner"}
        selected, targets = _select_step_up_topics(perf, recommended, limit=5)
        self.assertEqual(selected, ["OOP"])
        self.assertEqual(targets, {"OOP": "intermediate"})


class TestCreateDifficultyImprovementAssessment(unittest.TestCase):
    """Stage 7 — harder bank questions on familiar topics."""

    @patch("services.improvement_assessment_service._persist_bank_only_assessment")
    @patch("services.improvement_assessment_service._build_bank_only_rows")
    @patch(
        "services.improvement_assessment_service.employee_profile_service.get_employee_profile"
    )
    def test_creates_step_up_assessment(
        self,
        mock_profile: unittest.mock.MagicMock,
        mock_build: unittest.mock.MagicMock,
        mock_persist: unittest.mock.MagicMock,
    ) -> None:
        """Happy path: eligible topics get intermediate bank questions."""
        mock_profile.return_value = {
            "assessments_analyzed": 1,
            "topic_performance": [
                {
                    "topic_name": "OOP Basics",
                    "average_percent": 85.0,
                    "last_difficulty": "beginner",
                }
            ],
            "recommended_difficulty_by_topic": {"OOP Basics": "intermediate"},
        }
        mock_build.return_value = (
            [{"question_id": "1", "difficulty": "intermediate"}],
            0,
        )
        mock_persist.return_value = "ASM-STEP-1"

        result = create_difficulty_improvement_assessment("E1001", "python")

        self.assertEqual(result["assessment_id"], "ASM-STEP-1")
        self.assertEqual(result["selected_topics"], ["OOP Basics"])
        self.assertEqual(result["target_difficulty_by_topic"]["OOP Basics"], "intermediate")
        mock_build.assert_called_once()
        _args, kwargs = mock_build.call_args
        self.assertEqual(_args[1]["OOP Basics"], "intermediate")

    @patch(
        "services.improvement_assessment_service.employee_profile_service.get_employee_profile"
    )
    def test_no_step_up_ready_message(self, mock_profile: unittest.mock.MagicMock) -> None:
        """Low scores → no topics qualify for step-up."""
        mock_profile.return_value = {
            "assessments_analyzed": 1,
            "topic_performance": [
                {
                    "topic_name": "OOP",
                    "average_percent": 60.0,
                    "last_difficulty": "beginner",
                }
            ],
            "recommended_difficulty_by_topic": {"OOP": "beginner"},
        }

        result = create_difficulty_improvement_assessment("E1001", "python")

        self.assertIsNone(result["assessment_id"])
        self.assertIn("75%", result["availability_message"] or "")

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
        """Step-up path must never invoke LLM question generation."""
        mock_profile.return_value = {
            "assessments_analyzed": 1,
            "topic_performance": [
                {
                    "topic_name": "Topic A",
                    "average_percent": 90.0,
                    "last_difficulty": "beginner",
                }
            ],
            "recommended_difficulty_by_topic": {"Topic A": "intermediate"},
        }
        mock_build.return_value = ([{"question_id": "1"}], 0)
        mock_persist.return_value = "ASM-X"

        create_difficulty_improvement_assessment("E1001", "python")

        mock_llm.assert_not_called()


if __name__ == "__main__":
    unittest.main()
