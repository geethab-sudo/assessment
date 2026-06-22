"""Stage 9: hints, test cases in API responses, and LLM hint extraction."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from schemas.assessment import AssessmentResponse, QuestionOut
from services.assessment_service import _is_file_io_topic
from services.llm_service import _split_embedded_coding_hint


class TestQuestionOutStage9Fields(unittest.TestCase):
    """Participant API must expose hints and sample test cases (not strip them)."""

    def test_question_out_keeps_coding_hint(self) -> None:
        q = QuestionOut.model_validate(
            {
                "question_id": "1",
                "type": "coding",
                "question": "Write a function",
                "coding_hint": "use a loop",
            }
        )
        self.assertEqual(q.coding_hint, "use a loop")

    def test_assessment_response_preserves_nested_stage9_fields(self) -> None:
        payload = {
            "assessment_id": "ASM-TEST01",
            "found": True,
            "questions": [
                {
                    "question_id": "1",
                    "type": "coding",
                    "question": "Sum a list",
                    "sample_test_cases": [
                        {"input": "[1, 2]", "expected_output": "3", "label": "basic"}
                    ],
                    "coding_hint": "iterate",
                }
            ],
        }
        resp = AssessmentResponse.model_validate(payload)
        self.assertEqual(len(resp.questions[0].sample_test_cases), 1)
        self.assertEqual(resp.questions[0].coding_hint, "iterate")


class TestEmbeddedHintExtraction(unittest.TestCase):
    def test_trailing_hint_stripped_from_stem(self) -> None:
        prose, hint = _split_embedded_coding_hint(
            "Write sum(nums).\n\nhint: think about each element"
        )
        self.assertEqual(prose, "Write sum(nums).")
        self.assertEqual(hint, "think about each element")

    def test_no_hint_unchanged(self) -> None:
        prose, hint = _split_embedded_coding_hint("Only the question text")
        self.assertEqual(prose, "Only the question text")
        self.assertEqual(hint, "")


class TestFileIoTopicDetection(unittest.TestCase):
    def test_catalog_name_matches(self) -> None:
        name = "Tier 1 - Basic File I/O & Context Managers (with open statements)"
        self.assertTrue(_is_file_io_topic(name))

    def test_unrelated_topic(self) -> None:
        self.assertFalse(_is_file_io_topic("Tier 1 - OOP Basics"))


if __name__ == "__main__":
    unittest.main()
