"""Unit tests for participant shuffle utilities."""

from __future__ import annotations

import unittest

from services.shuffle_service import (
    apply_participant_shuffle,
    participant_seed,
    shuffle_mcq_options,
    shuffle_questions,
)


def _mcq(qid: str, opts: list[str]) -> dict:
    return {"question_id": qid, "type": "mcq", "options": list(opts), "question": f"Q{qid}"}


def _coding(qid: str) -> dict:
    return {"question_id": qid, "type": "coding", "options": [], "question": f"Q{qid}"}


class TestParticipantSeed(unittest.TestCase):
    def test_stable_for_same_inputs(self) -> None:
        a = participant_seed("assess-1", "E1001")
        b = participant_seed("assess-1", "E1001")
        self.assertEqual(a, b)

    def test_case_insensitive_employee_id(self) -> None:
        a = participant_seed("assess-1", "e1001")
        b = participant_seed("assess-1", "E1001")
        self.assertEqual(a, b)

    def test_different_employee_different_seed(self) -> None:
        a = participant_seed("assess-1", "E1001")
        b = participant_seed("assess-1", "E1002")
        self.assertNotEqual(a, b)


class TestShuffleQuestions(unittest.TestCase):
    def test_deterministic_order(self) -> None:
        qs = [_coding(str(i)) for i in range(1, 8)]
        seed = participant_seed("a1", "E1")
        o1 = [q["question_id"] for q in shuffle_questions(qs, seed)]
        o2 = [q["question_id"] for q in shuffle_questions(qs, seed)]
        self.assertEqual(o1, o2)
        self.assertNotEqual(o1, [str(i) for i in range(1, 8)])

    def test_different_seed_different_order(self) -> None:
        qs = [_coding(str(i)) for i in range(1, 11)]
        s1 = participant_seed("a1", "E1")
        s2 = participant_seed("a1", "E2")
        o1 = [q["question_id"] for q in shuffle_questions(qs, s1)]
        o2 = [q["question_id"] for q in shuffle_questions(qs, s2)]
        self.assertNotEqual(o1, o2)


class TestShuffleMcqOptions(unittest.TestCase):
    def test_shuffles_options_not_question_id(self) -> None:
        q = _mcq("1", ["A", "B", "C", "D"])
        seed = participant_seed("a1", "E1")
        out = shuffle_mcq_options(q, seed)
        self.assertEqual(out["question_id"], "1")
        self.assertEqual(sorted(out["options"]), ["A", "B", "C", "D"])
        self.assertNotEqual(out["options"], ["A", "B", "C", "D"])

    def test_stable_option_order_per_question(self) -> None:
        q = _mcq("2", ["w", "x", "y", "z"])
        seed = 12345
        o1 = shuffle_mcq_options(q, seed)["options"]
        o2 = shuffle_mcq_options(q, seed)["options"]
        self.assertEqual(o1, o2)


class TestApplyParticipantShuffle(unittest.TestCase):
    def test_empty_employee_id_unchanged(self) -> None:
        qs = [_mcq("1", ["a", "b"]), _coding("2")]
        out = apply_participant_shuffle("aid", "", qs)
        self.assertEqual([q["question_id"] for q in out], ["1", "2"])
        self.assertEqual(out[0]["options"], ["a", "b"])

    def test_apply_changes_order_and_mcq_options(self) -> None:
        qs = [_mcq("1", ["a", "b", "c", "d"]), _mcq("2", ["w", "x", "y", "z"]), _coding("3")]
        out = apply_participant_shuffle("aid", "E99", qs)
        ids = [q["question_id"] for q in out]
        self.assertEqual(set(ids), {"1", "2", "3"})
        self.assertNotEqual(ids, ["1", "2", "3"])
        for q in out:
            if q["type"] == "mcq":
                orig = next(x for x in qs if x["question_id"] == q["question_id"])
                self.assertEqual(sorted(q["options"]), sorted(orig["options"]))


if __name__ == "__main__":
    unittest.main()
