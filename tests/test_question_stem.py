"""MCQ stem and code_snippet normalization (``services.question_stem``).

Covers prettifying inline Python, splitting prose vs code for display, and
normalizing LLM output (discard stub ``def`` on write prompts; keep output snippets).
See TEST_GUIDE.md § IDs and low-level utilities.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.question_stem import (
    extract_inline_code_from_prose,
    extract_mixed_code_output_question,
    normalize_generated_question,
    prettify_inline_code,
    should_keep_stored_code,
    split_stem_for_display,
)


class TestQuestionStem(unittest.TestCase):
    """Display and storage rules for mixed prose/code MCQ stems."""

    def test_double_prettify_keeps_indent(self) -> None:
        """Running prettify twice must not break indentation (idempotent enough)."""
        raw = (
            "x = 5\n"
            "if x > 10: print('x is greater than 10')\n"
            "    else: print('x is less than or equal to 10')"
        )
        once = prettify_inline_code(raw)
        twice = prettify_inline_code(once)
        self.assertIn("    print('x is greater than 10')", twice)
        self.assertIn("    print('x is less than or equal to 10')", twice)

    def test_prettify_with_statement(self) -> None:
        """``with`` blocks expand to multi-line indented bodies."""
        raw = (
            "x = 5\n"
            "with open('example.txt', 'w') as f: f.write(str(x))\n"
            "with open('example.txt', 'r') as f: print(f.read())"
        )
        out = prettify_inline_code(raw)
        self.assertIn("with open('example.txt', 'w') as f:\n", out)
        self.assertIn("    f.write(str(x))", out)
        self.assertIn("    print(f.read())", out)

    def test_mixed_class_and_output_question(self) -> None:
        """Class definition glued to prose splits into stem + formatted code block."""
        raw = (
            "class Vehicle: def __init__(self, brand, model): self.__brand = brand\n"
            "self.__model = model. What is the output of the following code: "
            "print(Vehicle('Toyota', 'Camry')._Vehicle__brand):"
        )
        prose, code = split_stem_for_display(raw, "")
        self.assertIn("What is the output", prose)
        self.assertIn("class Vehicle:", code or "")
        self.assertIn("def __init__", code or "")
        self.assertIn("        self.__brand = brand", code or "")
        self.assertIn("        self.__model = model", code or "")
        self.assertIn("print(Vehicle", code or "")

    def test_prettify_if_else_multiline(self) -> None:
        """Mis-indented ``else`` on same line as ``if`` body is reformatted."""
        raw = (
            "x = 5\n"
            "if x > 10: print('x is greater than 10')\n"
            "    else: print('x is less than or equal to 10')"
        )
        out = prettify_inline_code(raw)
        self.assertIn("if x > 10:\n", out)
        self.assertIn("    print('x is greater than 10')", out)
        self.assertIn("else:\n", out)
        self.assertNotIn("    else:", out)

    def test_prettify_semicolon_one_liner(self) -> None:
        """Semicolon-separated one-liners break into readable multi-line code."""
        raw = (
            "x = 5; y = 3; if x > y: print('greater'); "
            "else: print('less or equal')"
        )
        out = prettify_inline_code(raw)
        self.assertIn("x = 5", out)
        self.assertIn("\n", out)
        self.assertIn("if x > y", out)

    def test_extract_inline_code_from_prose(self) -> None:
        """Trailing inline code after a colon moves from prose into code_snippet."""
        stem = (
            "What is the output of the following Python code snippet: "
            "x = 5; y = 3; if x > y: print('x is greater'); else: print('less')?"
        )
        prose, code = extract_inline_code_from_prose(stem)
        self.assertIn("output", prose.lower())
        self.assertIn("x = 5", code or "")
        self.assertNotIn("x = 5; y = 3", prose)

    def test_discard_stub_code_on_write_prompt(self) -> None:
        """Write-a-function prompts must not keep a one-line ``def`` stub as code."""
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
        """What-is-the-output questions keep the snippet in code_snippet."""
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
        """should_keep_stored_code rejects incomplete function stubs on write prompts."""
        self.assertFalse(
            should_keep_stored_code(
                "def find_max(numbers):",
                "Write a function to find the max in a list.",
                "mcq",
            )
        )


if __name__ == "__main__":
    unittest.main()
