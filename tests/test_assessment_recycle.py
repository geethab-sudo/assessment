"""Hybrid bank + LLM row building (``services.assessment_service`` Stage 2).

Tests ``_build_assessment_rows`` for admin **recycle_then_generate** (pull from
bank first, LLM fills gaps) vs **generate_new** (LLM only). No database required.
See TEST_GUIDE.md § Assessment generation and delivery.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from services.assessment_service import _build_assessment_rows


class TestBuildAssessmentRowsRecycle(unittest.TestCase):
    """Question source modes and shortage statistics."""

    def test_recycle_then_generate_mixes_bank_and_llm(self) -> None:
        """Bank supplies partial MCQs; LLM fills coding shortage; stats reflect both."""
        bank_mcqs = [
            {
                "bank_question_id": 101,
                "question": "Bank MCQ 1",
                "type": "mcq",
                "options": '["a","b"]',
                "correct_answer": "a",
                "topic_name": "Topic A",
                "code_snippet": "",
                "difficulty": "beginner",
            },
            {
                "bank_question_id": 102,
                "question": "Bank MCQ 2",
                "type": "mcq",
                "options": '["c","d"]',
                "correct_answer": "c",
                "topic_name": "Topic A",
                "code_snippet": "",
                "difficulty": "beginner",
            },
        ]

        def fake_find(
            topic_names,
            difficulty,
            n_needed,
            *,
            question_type=None,
            exclude_bank_ids=None,
            exclude_employee_id=None,
        ):
            if question_type == "mcq" and n_needed == 3:
                return bank_mcqs, 1
            if question_type == "coding" and n_needed == 1:
                return [], 1
            return [], n_needed

        llm_question = {
            "question": "New coding Q",
            "type": "coding",
            "options": [],
            "answer": "print(1)",
            "code_snippet": "",
        }

        with (
            patch(
                "services.assessment_service.question_bank_service.find_bank_questions",
                side_effect=fake_find,
            ),
            patch(
                "services.assessment_service._build_per_topic_strings",
                return_value={"Topic A": "Topic A"},
            ),
            patch(
                "services.assessment_service.generate_questions",
                return_value=[llm_question],
            ),
        ):
            rows, stats = _build_assessment_rows(
                "ASM-TEST",
                "beginner",
                "Topic A",
                "easy",
                ["mcq", "coding"],
                {"mcq": 3, "coding": 1},
                ["Topic A"],
                {"Topic A": {"mcq": 3, "coding": 1}},
                question_source="recycle_then_generate",
                target_employee_id="E1001",
            )

        self.assertEqual(len(rows), 4)
        self.assertEqual(stats["bank_sourced_count"], 2)
        self.assertEqual(stats["llm_generated_count"], 2)
        self.assertEqual(len(stats["shortage_messages"]), 2)
        bank_ids = {r.get("bank_question_id") for r in rows}
        self.assertEqual(bank_ids, {101, 102, None})

    def test_generate_new_uses_llm_only(self) -> None:
        """generate_new bypasses the bank and delegates entirely to per-topic LLM."""
        with patch(
            "services.assessment_service._generate_rows_per_topic",
            return_value=[{"question_id": "1", "type": "mcq", "question": "Q"}],
        ) as mock_gen:
            rows, stats = _build_assessment_rows(
                "ASM-TEST",
                "beginner",
                "Topic A",
                "easy",
                ["mcq"],
                {"mcq": 1},
                ["Topic A"],
                {"Topic A": {"mcq": 1}},
                question_source="generate_new",
            )

        mock_gen.assert_called_once()
        self.assertEqual(len(rows), 1)
        self.assertEqual(stats["bank_sourced_count"], 0)
        self.assertEqual(stats["llm_generated_count"], 1)


if __name__ == "__main__":
    unittest.main()
