"""Employee profile analytics (``services.employee_profile_service`` Stage 4A).

Tests proficiency labels, level-aware progress copy, topic merging across
assessments, scope filtering (last_3 vs full_history), weak topics, and
unexplored catalog topics per language.
See TEST_GUIDE.md § Employee analytics.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from services.employee_profile_service import (
    get_employee_profile,
    level_progress_label,
    proficiency_label,
    _merge_topic_performance,
    _pick_unexplored_for_recommendations,
    _recommended_difficulty,
    _unexplored_topic_names,
)


def _fake_record(
    aid: str,
    submitted_at: str,
    topics: dict[str, list[float]],
    *,
    language_code: str = "python",
) -> dict:
    """Build a minimal assessment record dict for profile unit tests."""
    questions = []
    for topic, scores in topics.items():
        for i, score in enumerate(scores):
            questions.append(
                {
                    "question_id": f"{aid}-q{i}",
                    "type": "mcq",
                    "topic_name": topic,
                    "score": score,
                    "correct": score >= 70,
                }
            )
    overall = sum(q["score"] for q in questions) / len(questions) if questions else 0
    return {
        "assessment_id": aid,
        "submitted_at": submitted_at,
        "language_code": language_code,
        "language_label": "Python",
        "overall_score": overall,
        "duration_seconds": 600,
        "display_name": "Test User",
        "topic_difficulty": {t: "beginner" for t in topics},
        "report": {
            "assessment_id": aid,
            "submitted_at": submitted_at,
            "overall_score": overall,
            "participant": {
                "employee_id": "E1001",
                "name": "Test User",
                "user_id": "E1001 | Test User",
            },
            "questions": questions,
            "topic_summary": [],
        },
    }


class TestProficiencyHelpers(unittest.TestCase):
    """Score → label mapping and within-level progress messaging."""

    def test_proficiency_labels_legacy(self) -> None:
        """Overall score bands map to Beginner / Intermediate / Advanced."""
        self.assertEqual(proficiency_label(40), "Beginner")
        self.assertEqual(proficiency_label(60), "Intermediate")
        self.assertEqual(proficiency_label(80), "Advanced")

    def test_level_progress_label_at_beginner(self) -> None:
        """Progress copy is relative to assessed difficulty, not global score tier."""
        self.assertEqual(level_progress_label(40, "beginner"), "Needs improvement")
        self.assertEqual(level_progress_label(68, "beginner"), "You're on the right path")
        self.assertEqual(
            level_progress_label(90, "beginner"),
            "You've conquered this level — ready for the next!",
        )

    def test_level_progress_label_at_advanced(self) -> None:
        """High score at advanced level uses mastery congratulation copy."""
        self.assertEqual(
            level_progress_label(85, "advanced"),
            "You've conquered this level — excellent mastery!",
        )

    def test_recommended_difficulty_step_up(self) -> None:
        """Strong performance within a band recommends stepping up one difficulty."""
        self.assertEqual(_recommended_difficulty(76, "beginner"), "intermediate")
        self.assertEqual(_recommended_difficulty(81, "intermediate"), "advanced")
        self.assertEqual(_recommended_difficulty(60, "beginner"), "beginner")


class TestMergeTopicPerformance(unittest.TestCase):
    """Aggregating per-topic scores across multiple assessment records."""

    def test_merges_across_assessments(self) -> None:
        """Same topic in two assessments increments questions_count and attempts."""
        records = [
            _fake_record("A1", "2026-01-01T00:00:00+00:00", {"OOP": [80.0]}),
            _fake_record("A2", "2026-02-01T00:00:00+00:00", {"OOP": [60.0]}),
        ]
        perf, _ = _merge_topic_performance(records)
        self.assertEqual(len(perf), 1)
        self.assertEqual(perf[0]["topic_name"], "OOP")
        self.assertEqual(perf[0]["questions_count"], 2)
        self.assertEqual(perf[0]["attempts"], 2)


@patch("services.employee_profile_service._catalog_topic_names")
@patch("services.employee_profile_service._load_assessment_records")
class TestGetEmployeeProfile(unittest.TestCase):
    """End-to-end profile assembly with mocked history and catalog."""

    def test_last_3_scope_limits_assessments(
        self, mock_load: unittest.mock.MagicMock, mock_catalog: unittest.mock.MagicMock
    ) -> None:
        """scope=last_3 analyzes at most three most recent assessments."""
        mock_catalog.return_value = ["OOP", "Exceptions", "New Topic"]
        mock_load.return_value = [
            _fake_record(f"A{i}", f"2026-0{i}-01T00:00:00+00:00", {"OOP": [50.0]})
            for i in range(1, 6)
        ]

        profile = get_employee_profile("E1001", scope="last_3")

        self.assertEqual(profile["assessments_analyzed"], 3)
        self.assertEqual(mock_load.call_count, 1)

    def test_full_history_explored_includes_old_assessment(
        self, mock_load: unittest.mock.MagicMock, mock_catalog: unittest.mock.MagicMock
    ) -> None:
        """full_history sees topics from older assessments outside last_3 window."""
        mock_catalog.return_value = ["Legacy Topic", "New Topic"]
        mock_load.return_value = [
            _fake_record("A5", "2026-05-01T00:00:00+00:00", {"OOP": [80.0]}),
            _fake_record("A4", "2026-04-01T00:00:00+00:00", {"OOP": [80.0]}),
            _fake_record("A3", "2026-03-01T00:00:00+00:00", {"OOP": [80.0]}),
            _fake_record("A1", "2026-01-01T00:00:00+00:00", {"Legacy Topic": [70.0]}),
        ]

        profile = get_employee_profile("E1001", scope="full_history")

        self.assertIn("Legacy Topic", profile["explored_topic_names"])
        self.assertIn("New Topic", profile["unexplored_topic_names"])
        self.assertNotIn("Legacy Topic", profile["unexplored_topic_names"])

    def test_weakest_topics_below_threshold(
        self, mock_load: unittest.mock.MagicMock, mock_catalog: unittest.mock.MagicMock
    ) -> None:
        """Topics below weak threshold appear in weakest_topics; strong ones do not."""
        mock_catalog.return_value = []
        mock_load.return_value = [
            _fake_record("A1", "2026-01-01T00:00:00+00:00", {"Weak": [40.0], "Strong": [90.0]}),
        ]

        profile = get_employee_profile("E1001", scope="last_3")

        self.assertIn("Weak", profile["weakest_topics"])
        self.assertNotIn("Strong", profile["weakest_topics"])

    def test_unexplored_limited_to_evaluated_languages(
        self, mock_load: unittest.mock.MagicMock, mock_catalog: unittest.mock.MagicMock
    ) -> None:
        """Unexplored topics only from languages the employee has actually assessed."""
        def catalog_for_lang(lang: str | None) -> list[str]:
            if lang in ("python", "py"):
                return ["Python Seen", "Python New"]
            if lang == "java":
                return ["Java Only Topic"]
            return []

        mock_catalog.side_effect = catalog_for_lang
        mock_load.return_value = [
            _fake_record(
                "A1",
                "2026-01-01T00:00:00+00:00",
                {"Python Seen": [80.0]},
                language_code="python",
            ),
        ]

        profile = get_employee_profile("E1001", scope="full_history")

        self.assertIn("Python New", profile["unexplored_topic_names"])
        self.assertNotIn("Java Only Topic", profile["unexplored_topic_names"])


class TestPickUnexploredForRecommendations(unittest.TestCase):
    """New-area topic selection follows preset pipeline, not highest tier first."""

    def test_prefers_tier_1_over_tier_2(self) -> None:
        unexplored = [
            "Tier 2 - Security",
            "Tier 1 - OOP Basics (Classes, Methods, Encapsulation)",
        ]
        picked = _pick_unexplored_for_recommendations(unexplored, limit=1)
        self.assertEqual(picked, ["Tier 1 - OOP Basics (Classes, Methods, Encapsulation)"])

    def test_intermediate_preset_before_remaining_tier_1(self) -> None:
        unexplored = [
            "Tier 1 - Packaging and virtual environments (venv)",
            "Tier 1 - OOP Basics (Classes, Methods, Encapsulation)",
        ]
        picked = _pick_unexplored_for_recommendations(unexplored, limit=1)
        self.assertEqual(picked, ["Tier 1 - OOP Basics (Classes, Methods, Encapsulation)"])


class TestUnexploredTopicNames(unittest.TestCase):
    """Catalog minus attempted topics, ordered for recommendation."""

    def test_per_language_exclusion(self) -> None:
        """Only unexplored topics for languages present in assessment history."""
        records = [
            _fake_record(
                "A1",
                "2026-01-01T00:00:00+00:00",
                {"OOP": [70.0]},
                language_code="python",
            ),
        ]
        with patch(
            "services.employee_profile_service._catalog_topic_names",
            side_effect=lambda lang: (
                ["OOP", "Concurrency"] if lang == "py" else ["Java Basics"]
            ),
        ), patch(
            "services.employee_profile_service._resolve_catalog_language_code",
            side_effect=lambda code, language_label=None: (
                "py" if (code or "").casefold() in ("python", "py") else code
            ),
        ):
            unexplored = _unexplored_topic_names(records)
        self.assertEqual(unexplored, ["Concurrency"])

    def test_includes_tier_2_when_not_attempted(self) -> None:
        """Unexplored list includes higher tiers; Tier 1 before Tier 2 in sort order."""
        records = [
            _fake_record(
                "A1",
                "2026-01-01T00:00:00+00:00",
                {"Tier 1 - OOP Basics": [80.0]},
                language_code="py",
            ),
        ]
        catalog = [
            "Tier 1 - OOP Basics",
            "Tier 1 - Logic & Flow Control",
            "Tier 2 - Security: PII",
        ]
        with patch(
            "services.employee_profile_service._catalog_topic_names",
            return_value=catalog,
        ), patch(
            "services.employee_profile_service._resolve_catalog_language_code",
            return_value="py",
        ):
            unexplored = _unexplored_topic_names(records)
        self.assertIn("Tier 2 - Security: PII", unexplored)
        self.assertIn("Tier 1 - Logic & Flow Control", unexplored)
        self.assertNotIn("Tier 1 - OOP Basics", unexplored)
        self.assertLess(
            unexplored.index("Tier 1 - Logic & Flow Control"),
            unexplored.index("Tier 2 - Security: PII"),
        )


if __name__ == "__main__":
    unittest.main()
