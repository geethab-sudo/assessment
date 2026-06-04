"""Unit tests for MCQ stem / code_snippet normalization."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.question_stem import (
    extract_inline_code_from_prose,
    normalize_generated_question,
    prettify_inline_code,
    should_keep_stored_code,
    split_stem_for_display,
)


class TestQuestionStem(unittest.TestCase):
    def test_prettify_semicolon_one_liner(self) -> None:
        raw = (
            "x = 5; y = 3; if x > y: print('greater'); "
            "else: print('less or equal')"
        )
        out = prettify_inline_code(raw)
        self.assertIn("x = 5", out)
        self.assertIn("\n", out)
        self.assertIn("if x > y", out)

    def test_extract_inline_code_from_prose(self) -> None:
        stem = (
            "What is the output of the following Python code snippet: "
            "x = 5; y = 3; if x > y: print('x is greater'); else: print('less')?"
        )
        prose, code = extract_inline_code_from_prose(stem)
        self.assertIn("output", prose.lower())
        self.assertIn("x = 5", code or "")
        self.assertNotIn("x = 5; y = 3", prose)

    def test_discard_stub_code_on_write_prompt(self) -> None:
        raw = {
            "id": 1,
            "type": "mcq",
            "question": (
                "Write a Python function to find the maximum value in a list. "
                "Return None if the list is empty."
            ),
            "code": "def find_max(numbers):",
            "options": ["a", "b", "c", "d"],
            "answer": "a",
        }
        out = normalize_generated_question(raw)
        self.assertEqual(out["code_snippet"], "")
        self.assertIn("Write a Python function", out["question"])

    def test_keep_inline_output_question(self) -> None:
        raw = {
            "id": 2,
            "type": "mcq",
            "question": (
                "What is the output of the following Python code snippet: "
                "print(2 + 2)?"
            ),
            "options": ["1", "2", "4", "Error"],
            "answer": "4",
        }
        out = normalize_generated_question(raw)
        self.assertIn("print(2 + 2)", out["code_snippet"])
        self.assertIn("output", out["question"].lower())

    def test_should_not_keep_stored_stub(self) -> None:
        self.assertFalse(
            should_keep_stored_code(
                "def find_max(numbers):",
                "Write a function to find the max in a list.",
                "mcq",
            )
        )


if __name__ == "__main__":
    unittest.main()
