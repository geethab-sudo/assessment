"""Unit tests for employee stats report (Stage 4B)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from services.employee_profile_service import get_employee_report


def _fake_record(aid: str, submitted_at: str, score: float) -> dict:
    return {
        "assessment_id": aid,
        "submitted_at": submitted_at,
        "language_code": "python",
        "language_label": "Python",
        "overall_score": score,
        "duration_seconds": 1200,
        "display_name": "Luis",
        "topic_difficulty": {"OOP": "beginner"},
        "report": {
            "submitted_at": submitted_at,
            "overall_score": score,
            "participant": {
                "employee_id": "E1001",
                "user_id": "E1001 | Luis",
            },
            "questions": [
                {
                    "question_id": "1",
                    "type": "mcq",
                    "topic_name": "OOP",
                    "score": score,
                    "correct": score >= 70,
                }
            ],
        },
    }


@patch("services.employee_profile_service.db_service.count_employee_needs_practice_bank_questions")
@patch("services.employee_profile_service.db_service.count_employee_mastered_by_topic")
@patch("services.employee_profile_service.get_employee_mastered_bank_ids")
@patch("services.employee_profile_service._load_assessment_records")
class TestGetEmployeeReport(unittest.TestCase):
    def test_empty_employee(
        self,
        mock_load: unittest.mock.MagicMock,
        mock_mastered: unittest.mock.MagicMock,
        mock_by_topic: unittest.mock.MagicMock,
        mock_needs: unittest.mock.MagicMock,
    ) -> None:
        mock_load.return_value = []
        mock_mastered.return_value = set()
        mock_by_topic.return_value = {}
        mock_needs.return_value = 0

        report = get_employee_report("E1001")

        self.assertEqual(report["summary"]["assessments_completed"], 0)
        self.assertEqual(report["summary"]["questions_answered"], 0)
        self.assertEqual(report["employee_id"], "E1001")

    def test_timeline_chronological_ascending(
        self,
        mock_load: unittest.mock.MagicMock,
        mock_mastered: unittest.mock.MagicMock,
        mock_by_topic: unittest.mock.MagicMock,
        mock_needs: unittest.mock.MagicMock,
    ) -> None:
        mock_load.return_value = [
            _fake_record("A2", "2026-02-01T00:00:00+00:00", 80.0),
            _fake_record("A1", "2026-01-01T00:00:00+00:00", 60.0),
        ]
        mock_mastered.return_value = {1, 2}
        mock_by_topic.return_value = {"OOP": 1}
        mock_needs.return_value = 0

        report = get_employee_report("E1001")

        timeline = report["score_timeline"]
        self.assertEqual(len(timeline), 2)
        self.assertEqual(timeline[0]["assessment_id"], "A1")
        self.assertEqual(timeline[1]["assessment_id"], "A2")

    def test_time_on_platform_sum(
        self,
        mock_load: unittest.mock.MagicMock,
        mock_mastered: unittest.mock.MagicMock,
        mock_by_topic: unittest.mock.MagicMock,
        mock_needs: unittest.mock.MagicMock,
    ) -> None:
        mock_load.return_value = [
            _fake_record("A1", "2026-01-01T00:00:00+00:00", 70.0),
            _fake_record("A2", "2026-02-01T00:00:00+00:00", 80.0),
        ]
        mock_mastered.return_value = set()
        mock_by_topic.return_value = {}
        mock_needs.return_value = 0

        report = get_employee_report("E1001")

        self.assertEqual(report["summary"]["total_time_seconds"], 2400)
        self.assertEqual(report["summary"]["avg_assessment_time_seconds"], 1200)
        self.assertEqual(report["display_name"], "Luis")

    def test_language_rollup(
        self,
        mock_load: unittest.mock.MagicMock,
        mock_mastered: unittest.mock.MagicMock,
        mock_by_topic: unittest.mock.MagicMock,
        mock_needs: unittest.mock.MagicMock,
    ) -> None:
        rec = _fake_record("A1", "2026-01-01T00:00:00+00:00", 75.0)
        mock_load.return_value = [rec]
        mock_mastered.return_value = set()
        mock_by_topic.return_value = {"OOP": 2}
        mock_needs.return_value = 1

        report = get_employee_report("E1001")

        self.assertEqual(len(report["languages"]), 1)
        self.assertEqual(report["languages"][0]["language_code"], "python")
        self.assertEqual(report["mastery"]["mastered_count"], 0)
        self.assertEqual(report["mastery"]["needs_practice_count"], 1)


if __name__ == "__main__":
    unittest.main()
