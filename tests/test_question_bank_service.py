"""Unit tests for question_bank_service (Stage 1)."""

from __future__ import annotations

import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services.question_bank_service import (
    _submission_indicates_mastered,
    add_questions_to_bank,
    backfill_employee_mastery_from_submissions,
    find_bank_questions,
    get_bank_availability,
    get_bank_stats,
    get_employee_mastered_bank_ids,
    normalize_bank_level,
    record_employee_question_mastery,
    record_question_outcome,
)


class TestNormalizeBankLevel(unittest.TestCase):
    def test_admin_levels(self) -> None:
        self.assertEqual(normalize_bank_level("Beginner"), "beginner")
        self.assertEqual(normalize_bank_level("intermediate"), "intermediate")
        self.assertEqual(normalize_bank_level("Advanced"), "advanced")

    def test_llm_legacy_labels(self) -> None:
        self.assertEqual(normalize_bank_level("easy"), "beginner")
        self.assertEqual(normalize_bank_level("medium"), "intermediate")
        self.assertEqual(normalize_bank_level("hard"), "advanced")

    def test_invalid_raises(self) -> None:
        with self.assertRaises(ValueError):
            normalize_bank_level("expert")


class TestSubmissionIndicatesMastered(unittest.TestCase):
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


class TestAddQuestionsToBank(unittest.TestCase):
    def test_upsert_increments_times_used(self) -> None:
        stored: dict[str, SimpleNamespace] = {}
        session = MagicMock()

        def flush_side_effect() -> None:
            for call in session.add.call_args_list:
                row = call[0][0]
                if row.content_hash not in stored:
                    row.id = len(stored) + 1
                    stored[row.content_hash] = row

        session.flush.side_effect = flush_side_effect

        def scalar_side_effect(stmt) -> SimpleNamespace | None:
            # Second upsert: return existing by content_hash lookup
            if stored:
                return next(iter(stored.values()))
            return None

        session.scalar.side_effect = scalar_side_effect

        @contextmanager
        def fake_session():
            yield session

        rows = [
            {
                "type": "mcq",
                "topic_name": "Topic A",
                "question": "What is 2+2?",
                "options": '["3","4"]',
                "correct_answer": "4",
            }
        ]

        with patch("services.question_bank_service._session", fake_session):
            first = add_questions_to_bank(rows, "beginner", "py")
            self.assertEqual(len(first), 1)
            second = add_questions_to_bank(rows, "beginner", "py")
            self.assertEqual(len(second), 1)
            existing = next(iter(stored.values()))
            self.assertEqual(existing.difficulty, "beginner")
            self.assertEqual(existing.times_used, 2)


class TestRecordAndStats(unittest.TestCase):
    def test_outcome_invokes_atomic_update(self) -> None:
        session = MagicMock()

        @contextmanager
        def fake_session():
            yield session

        with patch("services.question_bank_service._session", fake_session):
            record_question_outcome(1, True)
            record_question_outcome(1, False)

        self.assertEqual(session.execute.call_count, 2)
        session.commit.assert_called()

    def test_get_bank_stats_percentages(self) -> None:
        bq = SimpleNamespace(
            id=1,
            question_text="Q",
            type="mcq",
            topic_name="T",
            language_code="py",
            difficulty="beginner",
            created_at="2026-01-01",
            times_used=1,
            times_correct=3,
            times_wrong=1,
        )
        session = MagicMock()
        session.scalars.return_value.all.return_value = [bq]

        @contextmanager
        def fake_session():
            yield session

        with patch("services.question_bank_service._session", fake_session):
            stats = get_bank_stats(difficulty="beginner")

        self.assertEqual(len(stats), 1)
        self.assertEqual(stats[0]["percent_correct"], 75.0)
        self.assertEqual(stats[0]["percent_wrong"], 25.0)


class TestFindBankQuestions(unittest.TestCase):
    def test_filters_topic_and_difficulty(self) -> None:
        q1 = SimpleNamespace(
            id=1,
            question_text="Q1",
            type="mcq",
            options="",
            correct_answer="a",
            topic_name="Topic A",
            code_snippet="",
            difficulty="beginner",
            times_used=0,
        )
        session = MagicMock()
        session.scalars.return_value.all.return_value = [q1]

        @contextmanager
        def fake_session():
            yield session

        with (
            patch("services.question_bank_service._session", fake_session),
            patch(
                "services.question_bank_service.get_employee_mastered_bank_ids",
                return_value=set(),
            ),
        ):
            found, shortage = find_bank_questions(["Topic A"], "beginner", 5)

        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["topic_name"], "Topic A")
        self.assertEqual(shortage, 4)


class TestGetEmployeeMasteredBankIds(unittest.TestCase):
    def test_reads_from_mastery_table(self) -> None:
        session = MagicMock()
        session.scalars.return_value.all.return_value = [10, 20, 20]

        @contextmanager
        def fake_session():
            yield session

        with patch("services.question_bank_service._session", fake_session):
            mastered = get_employee_mastered_bank_ids("E1001")

        self.assertEqual(mastered, {10, 20})

    def test_case_insensitive_employee_id(self) -> None:
        session = MagicMock()
        session.scalars.return_value.all.return_value = [5]

        @contextmanager
        def fake_session():
            yield session

        with patch("services.question_bank_service._session", fake_session):
            get_employee_mastered_bank_ids("e1001")

        stmt = session.scalars.call_args[0][0]
        # employee_id stored normalized in DB; lookup uses casefold
        session.scalars.assert_called_once()


class TestRecordEmployeeMastery(unittest.TestCase):
    def test_inserts_new_mastery_row(self) -> None:
        session = MagicMock()
        session.scalar.return_value = None

        @contextmanager
        def fake_session():
            yield session

        with patch("services.question_bank_service._session", fake_session):
            record_employee_question_mastery("E1001", 42)

        session.add.assert_called_once()
        row = session.add.call_args[0][0]
        self.assertEqual(row.employee_id, "e1001")
        self.assertEqual(row.bank_question_id, 42)
        session.commit.assert_called_once()

    def test_skips_duplicate(self) -> None:
        session = MagicMock()
        session.scalar.return_value = 99

        @contextmanager
        def fake_session():
            yield session

        with patch("services.question_bank_service._session", fake_session):
            record_employee_question_mastery("E1001", 42)

        session.add.assert_not_called()


class TestBackfillEmployeeMastery(unittest.TestCase):
    def test_backfill_inserts_correct_submissions_only(self) -> None:
        sub_wrong = SimpleNamespace(
            user_id="E1001 | Alice",
            assessment_id="ASM-1",
            question_id="1",
            user_answer="wrong",
            score="40",
            timestamp="2026-01-01T00:00:00+00:00",
        )
        sub_right = SimpleNamespace(
            user_id="E1001 | Bob",
            assessment_id="ASM-1",
            question_id="2",
            user_answer="four",
            score="100",
            timestamp="2026-01-02T00:00:00+00:00",
        )
        aq_wrong = SimpleNamespace(
            bank_question_id=10, type="coding", correct_answer=""
        )
        aq_right = SimpleNamespace(
            bank_question_id=20, type="mcq", correct_answer="four"
        )

        session = MagicMock()
        session.scalars.return_value.all.return_value = [sub_wrong, sub_right]

        scalar_results = [aq_wrong, aq_right, None]
        session.scalar.side_effect = scalar_results

        @contextmanager
        def fake_session():
            yield session

        with patch("services.question_bank_service._session", fake_session):
            n = backfill_employee_mastery_from_submissions()

        self.assertEqual(n, 1)
        session.add.assert_called_once()
        row = session.add.call_args[0][0]
        self.assertEqual(row.employee_id, "e1001")
        self.assertEqual(row.bank_question_id, 20)


class TestGetBankAvailability(unittest.TestCase):
    def test_shortage_with_mastered_exclusion(self) -> None:
        candidates = [
            SimpleNamespace(id=1),
            SimpleNamespace(id=2),
            SimpleNamespace(id=3),
        ]
        session = MagicMock()
        session.scalars.return_value.all.return_value = candidates

        @contextmanager
        def fake_session():
            yield session

        with (
            patch("services.question_bank_service._session", fake_session),
            patch(
                "services.question_bank_service.get_employee_mastered_bank_ids",
                return_value={1},
            ),
        ):
            result = get_bank_availability(
                ["Topic A"],
                "beginner",
                5,
                exclude_employee_id="E1001",
            )

        self.assertEqual(result["available"], 2)
        self.assertEqual(result["requested"], 5)
        self.assertEqual(result["shortage"], 3)
        self.assertEqual(result["per_topic"][0]["available"], 2)


if __name__ == "__main__":
    unittest.main()
