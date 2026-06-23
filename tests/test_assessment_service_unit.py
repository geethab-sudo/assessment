"""
Unit tests for assessment_service helpers that don't need a DB or LLM.

Covers options parsing, grading rules, routing flags, row builders, notebook
templates, and already_submitted blocking on repeat load. See TEST_GUIDE.md.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.assessment_service import (
    SCORE_CORRECT_THRESHOLD,
    _compute_routing_flag,
    _generate_rows_legacy,
    _generate_rows_per_topic,
    _is_answer_correct,
    _options_for_csv,
    _parse_options,
    _row_from_question,
    _score_to_unit,
    build_notebook_template,
    get_assessment_for_user,
)


class TestOptionsForCsv(unittest.TestCase):
    """Serialize MCQ options for CSV/database storage."""

    def test_none_returns_empty(self):
        self.assertEqual(_options_for_csv(None), "")

    def test_string_passthrough(self):
        self.assertEqual(_options_for_csv('["a","b"]'), '["a","b"]')

    def test_list_serialised(self):
        result = _options_for_csv(["A", "B", "C"])
        self.assertIn('"A"', result)
        self.assertIn('"C"', result)

    def test_unserializable_returns_empty(self):
        self.assertEqual(_options_for_csv(object()), "")


class TestParseOptions(unittest.TestCase):
    """Parse stored options JSON back to a list for grading/display."""

    def test_empty_string(self):
        self.assertEqual(_parse_options(""), [])

    def test_valid_json_list(self):
        self.assertEqual(_parse_options('["a","b"]'), ["a", "b"])

    def test_dict_returns_values(self):
        self.assertEqual(_parse_options('{"x":"a","y":"b"}'), ["a", "b"])

    def test_invalid_json_returns_empty(self):
        self.assertEqual(_parse_options("not json"), [])


class TestIsAnswerCorrect(unittest.TestCase):
    """Per-question-type correctness rules including coding score threshold."""

    def test_mcq_case_insensitive_match(self):
        self.assertTrue(_is_answer_correct("mcq", "  Answer A  ", "answer a", 0.0))

    def test_mcq_wrong_answer(self):
        self.assertFalse(_is_answer_correct("mcq", "B", "A", 0.0))

    def test_coding_above_threshold(self):
        self.assertTrue(_is_answer_correct("coding", "any", "", SCORE_CORRECT_THRESHOLD))

    def test_coding_below_threshold(self):
        self.assertFalse(_is_answer_correct("coding", "any", "", SCORE_CORRECT_THRESHOLD - 1))

    def test_subjective_uses_score(self):
        self.assertTrue(_is_answer_correct("subjective", "x", "", 80.0))


class TestRowFromQuestion(unittest.TestCase):
    """Convert LLM question dict to assessment_questions row shape."""

    def test_basic_structure(self):
        q = {"question": "What?", "type": "mcq", "options": ["a", "b"], "answer": "a"}
        row = _row_from_question(q, 3, "Topic A")
        self.assertEqual(row["question_id"], "3")
        self.assertEqual(row["topic_name"], "Topic A")
        self.assertEqual(row["type"], "mcq")
        self.assertIn('"a"', row["options"])

    def test_missing_code_snippet_defaults_empty(self):
        q = {"question": "Q", "type": "coding", "answer": ""}
        row = _row_from_question(q, 1, "")
        self.assertEqual(row["code_snippet"], "")

    def test_stage9_fields_preserved(self):
        q = {
            "question": "Write sum(nums)",
            "type": "coding",
            "answer": "def sum(nums): ...",
            "sample_test_cases": [{"input": "[1,2]", "expected_output": "3"}],
            "coding_hint": "try a loop",
        }
        row = _row_from_question(q, 2, "Basics")
        self.assertEqual(len(row["sample_test_cases"]), 1)
        self.assertEqual(row["coding_hint"], "try a loop")


class TestScoreToUnit(unittest.TestCase):
    def test_converts_hundred_scale(self):
        self.assertEqual(_score_to_unit(70.0), 0.7)
        self.assertEqual(_score_to_unit(100.0), 1.0)
        self.assertEqual(_score_to_unit(0.0), 0.0)

    def test_clamps_out_of_range(self):
        self.assertEqual(_score_to_unit(150.0), 1.0)
        self.assertEqual(_score_to_unit(-5.0), 0.0)


class TestComputeRoutingFlag(unittest.TestCase):
    """pyodide | jupyter | mixed from topic modality lists."""

    def test_empty_topics_is_pyodide(self):
        self.assertEqual(_compute_routing_flag([]), "pyodide")

    def test_all_pyodide_topics(self):
        with patch(
            "services.assessment_service.jupyter_topic_names_from_list",
            return_value=[],
        ):
            self.assertEqual(_compute_routing_flag(["Topic A", "Topic B"]), "pyodide")

    def test_all_jupyter_topics(self):
        names = ["Jupyter Topic"]
        with patch(
            "services.assessment_service.jupyter_topic_names_from_list",
            return_value=names,
        ):
            self.assertEqual(_compute_routing_flag(names), "jupyter")

    def test_mixed_topics(self):
        names = ["Pyodide Topic", "Jupyter Topic"]
        with patch(
            "services.assessment_service.jupyter_topic_names_from_list",
            return_value=["Jupyter Topic"],
        ):
            self.assertEqual(_compute_routing_flag(names), "mixed")


class TestBuildNotebookTemplate(unittest.TestCase):
    """nbformat 4 notebook skeleton for Jupyter coding assessments."""

    def test_empty_questions_produces_no_cells(self):
        nb = build_notebook_template([], "test-id")
        self.assertEqual(nb["cells"], [])
        self.assertEqual(nb["nbformat"], 4)

    def test_one_question_produces_markdown_and_code_cell(self):
        qs = [{"question": "Explain closures.", "question_id": "1", "topic_name": ""}]
        nb = build_notebook_template(qs, "test-id")
        self.assertEqual(len(nb["cells"]), 2)
        self.assertEqual(nb["cells"][0]["cell_type"], "markdown")
        self.assertEqual(nb["cells"][1]["cell_type"], "code")
        self.assertIn("Explain closures.", nb["cells"][0]["source"][1])

    def test_multiple_questions_numbered_correctly(self):
        qs = [
            {"question": "Q1", "question_id": "1", "topic_name": ""},
            {"question": "Q2", "question_id": "2", "topic_name": ""},
        ]
        nb = build_notebook_template(qs, "test-id")
        self.assertIn("# Question 1", nb["cells"][0]["source"][0])
        self.assertIn("# Question 2", nb["cells"][2]["source"][0])


class TestGenerateRowsLegacy(unittest.TestCase):
    """Single-topic LLM generation path (pre per-topic config)."""

    def test_mismatched_types_raises(self):
        with self.assertRaises(ValueError):
            _generate_rows_legacy("id", "topic", "easy", ["mcq"], {"coding": 1})

    def test_returns_rows_from_llm(self):
        fake_questions = [
            {"question": "Q?", "type": "mcq", "options": ["a"], "answer": "a", "id": 1}
        ]
        with patch(
            "services.assessment_service.generate_questions",
            return_value=fake_questions,
        ):
            rows = _generate_rows_legacy("id", "topic", "easy", ["mcq"], {"mcq": 1})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["topic_name"], "")


class TestGenerateRowsPerTopic(unittest.TestCase):
    """Per-topic LLM calls with global sequential question_id assignment."""

    def test_skips_topics_with_no_matching_type(self):
        per_topic = {
            "Topic A": {"mcq": 2},
            "Topic B": {},  # nothing configured
        }
        with patch(
            "services.assessment_service.generate_questions",
            return_value=[
                {"question": "Q?", "type": "mcq", "options": [], "answer": "a"}
            ],
        ) as mock_gen:
            rows = _generate_rows_per_topic(
                "aid", ["Topic A", "Topic B"], {"Topic A": "Topic A", "Topic B": "Topic B"},
                "easy", ["mcq"], per_topic,
            )
        # Only Topic A should have triggered an LLM call
        self.assertEqual(mock_gen.call_count, 1)
        self.assertEqual(rows[0]["topic_name"], "Topic A")

    def test_global_question_ids_are_sequential(self):
        per_topic = {"T1": {"mcq": 1}, "T2": {"mcq": 1}}
        fake_q = {"question": "Q?", "type": "mcq", "options": [], "answer": "a"}
        with patch(
            "services.assessment_service.generate_questions",
            return_value=[fake_q],
        ):
            rows = _generate_rows_per_topic(
                "aid", ["T1", "T2"], {"T1": "T1", "T2": "T2"},
                "easy", ["mcq"], per_topic,
            )
        self.assertEqual(rows[0]["question_id"], "1")
        self.assertEqual(rows[1]["question_id"], "2")


class TestGetAssessmentForUserAlreadySubmitted(unittest.TestCase):
    """Repeat load after submit must set already_submitted (timed and untimed)."""

    @patch("services.assessment_service.notebook_plan_for_assessment")
    @patch("services.assessment_service.attempt_service.user_has_submitted")
    @patch("services.assessment_service.db_service.read_questions_by_assessment")
    @patch("services.assessment_service.db_service.get_assessment_metadata")
    def test_blocks_repeat_attempt_for_untimed_assessment(
        self,
        mock_meta: MagicMock,
        mock_rows: MagicMock,
        mock_submitted: MagicMock,
        mock_plan: MagicMock,
    ) -> None:
        """Untimed assessment with prior submit returns empty questions + flag."""
        mock_meta.return_value = {
            "language_code": "py",
            "routing_flag": "pyodide",
            "topic_names": ["Topic A"],
            "jupyter_topic_names": [],
            "is_timed": False,
        }
        mock_rows.return_value = [
            {"question_id": "1", "type": "mcq", "question": "Q?", "options": "[]"},
        ]
        mock_submitted.return_value = True
        mock_plan.return_value = {
            "notebook_expected": False,
            "notebook_ready": False,
            "expected_notebook_coding_count": 0,
            "actual_notebook_coding_count": 0,
        }

        out = get_assessment_for_user("ASM-TEST01", employee_id="C002")

        self.assertTrue(out["already_submitted"])
        self.assertEqual(out["questions"], [])


if __name__ == "__main__":
    unittest.main()
