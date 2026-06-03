"""
Deterministic per-participant shuffling for assessment delivery.

Seed is derived from assessment_id + employee_id only (not participant name).
"""

from __future__ import annotations

import hashlib
import random
from typing import Any


def participant_seed(assessment_id: str, employee_id: str) -> int:
    """Stable 64-bit seed from assessment and employee identifiers."""
    key = f"{assessment_id.strip().casefold()}|{employee_id.strip().casefold()}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _options_subseed(base_seed: int, question_id: str) -> int:
    h = hashlib.sha256(f"{base_seed}|{question_id}".encode("utf-8")).hexdigest()
    return int(h[:16], 16)


def shuffle_questions(questions: list[dict[str, Any]], seed: int) -> list[dict[str, Any]]:
    """Return a new list with questions in shuffled order."""
    rng = random.Random(seed)
    out = list(questions)
    rng.shuffle(out)
    return out


def shuffle_mcq_options(question: dict[str, Any], seed: int) -> dict[str, Any]:
    """Return a copy of the question with MCQ options shuffled (if applicable)."""
    q = dict(question)
    if (q.get("type") or "").lower() != "mcq":
        return q
    opts = q.get("options")
    if not isinstance(opts, list) or len(opts) <= 1:
        return q
    opts_copy = list(opts)
    qid = str(q.get("question_id", ""))
    rng = random.Random(_options_subseed(seed, qid))
    rng.shuffle(opts_copy)
    q["options"] = opts_copy
    return q


def apply_participant_shuffle(
    assessment_id: str,
    employee_id: str,
    questions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Shuffle question order and MCQ option order for one participant.

    Same assessment_id + employee_id always yields the same layout.
    """
    eid = employee_id.strip()
    if not eid:
        return questions
    seed = participant_seed(assessment_id, eid)
    ordered = shuffle_questions(questions, seed)
    return [shuffle_mcq_options(q, seed) for q in ordered]
