"""Question bank service (``services.question_bank_service`` Stage 1).

Pure unit tests for normalization and correctness rules. Mongo-backed flows
are covered in ``test_mongodb_integration.py``.
"""

from __future__ import annotations

import unittest

from services.question_bank_service import (
    _submission_indicates_mastered,
    infer_bank_level_from_topic,
    normalize_bank_level,
)


class TestNormalizeBankLevel(unittest.TestCase):
    """Map admin/LLM difficulty labels to canonical beginner|intermediate|advanced."""

    def test_admin_levels(self) -> None:
        self.assertEqual(normalize_bank_level("Beginner"), "beginner")
        self.assertEqual(normalize_bank_level("intermediate"), "intermediate")
        self.assertEqual(normalize_bank_level("Advanced"), "advanced")

    def test_llm_legacy_labels(self) -> None:
        """Legacy easy/medium/hard from LLM map to the three bank levels."""

        self.assertEqual(normalize_bank_level("easy"), "beginner")
        self.assertEqual(normalize_bank_level("medium"), "intermediate")
        self.assertEqual(normalize_bank_level("hard"), "advanced")

    def test_invalid_raises(self) -> None:
        """Unknown difficulty strings raise ValueError."""

        with self.assertRaises(ValueError):
            normalize_bank_level("expert")


class TestInferBankLevelFromTopic(unittest.TestCase):
    """Derive bank level from Tier N topic name prefix or explicit override."""

    def test_tier_prefixes(self) -> None:
        self.assertEqual(
            infer_bank_level_from_topic(
                "Tier 1 - Logic & Flow Control (Conditionals, Loops, Comprehensions)"
            ),
            "beginner",
        )
        self.assertEqual(
            infer_bank_level_from_topic(
                "Tier 2 - Security: PII/Credit card Regex redaction strings"
            ),
            "intermediate",
        )
        self.assertEqual(
            infer_bank_level_from_topic("Tier 3 - Advanced topic"),
            "advanced",
        )

    def test_explicit_difficulty_wins(self) -> None:
        """When difficulty is provided explicitly, it overrides tier inference."""

        self.assertEqual(
            infer_bank_level_from_topic("Tier 1 - X", explicit_difficulty="advanced"),
            "advanced",
        )


class TestSubmissionIndicatesMastered(unittest.TestCase):
    """Whether a single submission counts as mastering a bank question."""

    def test_mcq_correct(self) -> None:
        self.assertTrue(
            _submission_indicates_mastered("mcq", "Answer A", "answer a", "0")
        )

    def test_mcq_wrong(self) -> None:
        self.assertFalse(
            _submission_indicates_mastered("mcq", "B", "A", "100")
        )

    def test_coding_at_threshold(self) -> None:
        self.assertTrue(
            _submission_indicates_mastered("coding", "code", "", "70")
        )

    def test_coding_below_threshold(self) -> None:
        self.assertFalse(
            _submission_indicates_mastered("coding", "code", "", "69.9")
        )


if __name__ == "__main__":
    unittest.main()
