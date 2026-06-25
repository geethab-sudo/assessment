"""
Question Bank — canonical reusable question store with analytics counters.

Every confirmed assessment question is automatically upserted here.
Questions can be recycled across assessments while excluding questions
a specific employee has already mastered (answered correctly).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from services.database import coll, next_id


ALLOWED_BANK_LEVELS = frozenset({"beginner", "intermediate", "advanced"})
_LLM_DIFFICULTY_TO_LEVEL = {
    "easy": "beginner",
    "medium": "intermediate",
    "hard": "advanced",
}


def normalize_bank_level(value: str) -> str:
    """Return canonical bank level: beginner | intermediate | advanced."""
    v = (value or "").strip().lower()
    if v in ALLOWED_BANK_LEVELS:
        return v
    mapped = _LLM_DIFFICULTY_TO_LEVEL.get(v)
    if mapped:
        return mapped
    raise ValueError(
        f"Invalid bank level/difficulty: {value!r}. "
        "Expected beginner, intermediate, advanced (or easy, medium, hard)."
    )


def infer_bank_level_from_topic(
    topic_name: str,
    *,
    explicit_difficulty: str | None = None,
) -> str:
    """
    Infer bank level for legacy rows missing ``assessment_questions.difficulty``.

    Tier 1 catalog topics → beginner; Tier 2 → intermediate; Tier 3 → advanced.
    """
    if explicit_difficulty:
        try:
            return normalize_bank_level(explicit_difficulty)
        except ValueError:
            pass
    topic = (topic_name or "").strip()
    if topic.startswith("Tier 2"):
        return "intermediate"
    if topic.startswith("Tier 3"):
        return "advanced"
    return "beginner"


def _content_hash(qtype: str, topic_name: str, question_text: str) -> str:
    payload = f"{qtype.strip().lower()}|{topic_name.strip()}|{question_text.strip()[:1000]}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_questions_to_bank(
    rows: list[dict[str, Any]],
    level: str,
    language_code: str | None = None,
) -> dict[str, int]:
    """
    Upsert question rows into the bank. Returns mapping of content_hash → bank id.

    ``level`` is stored as beginner | intermediate | advanced (admin API level).
    """
    if not rows:
        return {}

    diff = normalize_bank_level(level)
    lang = (language_code or "").strip()[:32] or None
    hash_to_id: dict[str, int] = {}
    bank = coll("question_bank")

    for row in rows:
        qtype = (row.get("type") or "").strip().lower()
        topic = (row.get("topic_name") or "").strip()
        qtext = (row.get("question") or "").strip()
        if not qtext or not qtype:
            continue

        ch = _content_hash(qtype, topic, qtext)
        existing = bank.find_one({"content_hash": ch})
        if existing:
            bank.update_one(
                {"content_hash": ch},
                {"$inc": {"times_used": 1}},
            )
            hash_to_id[ch] = int(existing["id"])
        else:
            bank_id = next_id("question_bank")
            bank.insert_one(
                {
                    "id": bank_id,
                    "content_hash": ch,
                    "question_text": qtext,
                    "type": qtype,
                    "options": row.get("options", "") or "",
                    "correct_answer": row.get("correct_answer", "") or "",
                    "code_snippet": row.get("code_snippet") or None,
                    "topic_name": topic,
                    "language_code": lang,
                    "difficulty": diff,
                    "created_at": _utc_now_iso(),
                    "times_used": 1,
                    "times_correct": 0,
                    "times_wrong": 0,
                    "sample_test_cases": row.get("sample_test_cases"),
                    "coding_hint": row.get("coding_hint") or None,
                }
            )
            hash_to_id[ch] = bank_id

    return hash_to_id


def _topic_name_for_bank_row(
    aq: dict[str, Any],
    assessment: dict[str, Any] | None,
) -> str:
    topic = (aq.get("topic_name") or "").strip()
    if topic:
        return topic
    if not assessment:
        return ""
    names = assessment.get("topic_names") or []
    if not isinstance(names, list):
        return ""
    for raw in names:
        candidate = str(raw or "").strip()
        if candidate:
            return candidate
    return ""


def backfill_question_bank_from_assessment_questions() -> int:
    """
    Import legacy ``assessment_questions`` into ``question_bank`` and link rows.

    Idempotent: uses the same content-hash dedup as ``add_questions_to_bank``.
    Returns the number of assessment question rows newly linked to the bank.
    """
    linked = 0
    aq_coll = coll("assessment_questions")
    bank = coll("question_bank")
    assessments = coll("assessments")

    aq_rows = list(
        aq_coll.find({"bank_question_id": None}).sort("id", 1)
    )
    assessment_cache: dict[str, dict[str, Any] | None] = {}

    def _assessment_for(aid: str) -> dict[str, Any] | None:
        if aid not in assessment_cache:
            assessment_cache[aid] = assessments.find_one({"assessment_id": aid})
        return assessment_cache[aid]

    for aq in aq_rows:
        qtype = (aq.get("type") or "").strip().lower()
        qtext = (aq.get("question") or "").strip()
        if not qtype or not qtext:
            continue

        assessment = _assessment_for(aq["assessment_id"])
        topic = _topic_name_for_bank_row(aq, assessment)
        if not topic:
            continue

        level = infer_bank_level_from_topic(
            topic,
            explicit_difficulty=aq.get("difficulty"),
        )
        lang = None
        if assessment and assessment.get("language_code"):
            lang = (assessment["language_code"] or "").strip()[:32] or None

        ch = _content_hash(qtype, topic, qtext)
        existing = bank.find_one({"content_hash": ch})
        if existing:
            bank.update_one(
                {"content_hash": ch},
                {"$inc": {"times_used": 1}},
            )
            bank_id = int(existing["id"])
        else:
            bank_id = next_id("question_bank")
            bank.insert_one(
                {
                    "id": bank_id,
                    "content_hash": ch,
                    "question_text": qtext,
                    "type": qtype,
                    "options": aq.get("options") or "",
                    "correct_answer": aq.get("correct_answer") or "",
                    "code_snippet": aq.get("code_snippet") or None,
                    "topic_name": topic,
                    "language_code": lang,
                    "difficulty": level,
                    "created_at": _utc_now_iso(),
                    "times_used": 1,
                    "times_correct": 0,
                    "times_wrong": 0,
                }
            )

        update_fields: dict[str, Any] = {"bank_question_id": bank_id}
        if not aq.get("difficulty"):
            update_fields["difficulty"] = level
        aq_coll.update_one({"_id": aq["_id"]}, {"$set": update_fields})
        linked += 1

    return linked


def link_assessment_questions_to_bank(
    assessment_id: str,
    hash_to_bank_id: dict[str, int],
    level: str,
) -> None:
    """Set bank_question_id and difficulty on matching assessment_question rows."""
    if not hash_to_bank_id:
        return

    diff = normalize_bank_level(level)
    aq_coll = coll("assessment_questions")

    for aq in aq_coll.find({"assessment_id": assessment_id}):
        qtype = (aq.get("type") or "").strip().lower()
        topic = (aq.get("topic_name") or "").strip()
        qtext = (aq.get("question") or "").strip()
        ch = _content_hash(qtype, topic, qtext)
        bank_id = hash_to_bank_id.get(ch)
        if bank_id is not None:
            aq_coll.update_one(
                {"_id": aq["_id"]},
                {"$set": {"bank_question_id": bank_id, "difficulty": diff}},
            )


def increment_question_usage(bank_question_id: int) -> None:
    coll("question_bank").update_one(
        {"id": int(bank_question_id)},
        {"$inc": {"times_used": 1}},
    )


def record_question_outcome(bank_question_id: int | None, correct: bool) -> None:
    if bank_question_id is None:
        return
    field = "times_correct" if correct else "times_wrong"
    coll("question_bank").update_one(
        {"id": int(bank_question_id)},
        {"$inc": {field: 1}},
    )


def record_employee_question_mastery(
    employee_id: str,
    bank_question_id: int | None,
) -> None:
    from services.attempt_service import normalize_employee_id

    if bank_question_id is None:
        return
    eid = normalize_employee_id(employee_id)
    if not eid:
        return

    mastery = coll("employee_question_mastery")
    if mastery.find_one(
        {"employee_id": eid, "bank_question_id": int(bank_question_id)},
        projection={"_id": 1},
    ):
        return
    mastery.insert_one(
        {
            "id": next_id("employee_question_mastery"),
            "employee_id": eid,
            "bank_question_id": int(bank_question_id),
            "mastered_at": _utc_now_iso(),
        }
    )


def backfill_employee_mastery_from_submissions() -> int:
    from services.attempt_service import (
        normalize_employee_id,
        parse_employee_id_from_user_label,
    )

    inserted = 0
    subs = coll("submissions").find({"question_id": {"$ne": "notebook"}})
    mastery = coll("employee_question_mastery")
    aq_coll = coll("assessment_questions")

    for sub in subs:
        eid = normalize_employee_id(
            parse_employee_id_from_user_label(sub.get("user_id") or "")
        )
        if not eid:
            continue

        aq = aq_coll.find_one(
            {
                "assessment_id": sub["assessment_id"],
                "question_id": sub["question_id"],
            }
        )
        if not aq or aq.get("bank_question_id") is None:
            continue

        if not _submission_indicates_mastered(
            aq.get("type") or "",
            sub.get("user_answer") or "",
            aq.get("correct_answer") or "",
            sub.get("score") or "",
        ):
            continue

        bid = int(aq["bank_question_id"])
        if mastery.find_one(
            {"employee_id": eid, "bank_question_id": bid},
            projection={"_id": 1},
        ):
            continue

        mastery.insert_one(
            {
                "id": next_id("employee_question_mastery"),
                "employee_id": eid,
                "bank_question_id": bid,
                "mastered_at": sub.get("timestamp") or _utc_now_iso(),
            }
        )
        inserted += 1

    return inserted


def _submission_indicates_mastered(
    qtype: str,
    user_answer: str,
    correct_answer: str,
    score_text: str,
) -> bool:
    from services.assessment_service import _is_answer_correct

    try:
        score = float(score_text or 0)
    except (TypeError, ValueError):
        score = 0.0
    return _is_answer_correct(
        (qtype or "").strip().lower(),
        user_answer or "",
        correct_answer or "",
        score,
    )


def get_employee_mastered_bank_ids(employee_id: str) -> set[int]:
    from services.attempt_service import normalize_employee_id

    eid = normalize_employee_id(employee_id)
    if not eid:
        return set()

    rows = coll("employee_question_mastery").find(
        {"employee_id": eid},
        {"bank_question_id": 1},
    )
    return {int(r["bank_question_id"]) for r in rows}


def find_bank_questions(
    topic_names: list[str],
    difficulty: str,
    n_needed: int,
    *,
    question_type: str | None = None,
    exclude_bank_ids: set[int] | None = None,
    exclude_employee_id: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    if n_needed <= 0 or not topic_names:
        return [], max(0, n_needed)

    diff = normalize_bank_level(difficulty)
    qtype_filter = (question_type or "").strip().lower() or None
    names = [n.strip() for n in topic_names if n and n.strip()]
    if not names:
        return [], n_needed

    all_excluded: set[int] = set(exclude_bank_ids or set())
    if exclude_employee_id:
        all_excluded |= get_employee_mastered_bank_ids(exclude_employee_id)

    query: dict[str, Any] = {
        "topic_name": {"$in": names},
        "difficulty": diff,
    }
    if qtype_filter:
        query["type"] = qtype_filter

    candidates = list(
        coll("question_bank")
        .find(query)
        .sort([("times_used", 1), ("id", 1)])
    )

    found: list[dict[str, Any]] = []
    for bq in candidates:
        if int(bq["id"]) in all_excluded:
            continue
        if len(found) >= n_needed:
            break
        found.append(
            {
                "bank_question_id": bq["id"],
                "question": bq["question_text"],
                "type": bq["type"],
                "options": bq.get("options") or "",
                "correct_answer": bq.get("correct_answer") or "",
                "topic_name": bq.get("topic_name") or "",
                "code_snippet": bq.get("code_snippet") or "",
                "difficulty": bq["difficulty"],
                "sample_test_cases": bq.get("sample_test_cases"),
                "coding_hint": bq.get("coding_hint") or "",
            }
        )

    shortage = max(0, n_needed - len(found))
    return found, shortage


def get_bank_stats(
    *,
    topic_name: str | None = None,
    difficulty: str | None = None,
    language_code: str | None = None,
    question_type: str | None = None,
) -> list[dict[str, Any]]:
    query: dict[str, Any] = {}
    if topic_name:
        query["topic_name"] = topic_name.strip()
    if difficulty:
        query["difficulty"] = normalize_bank_level(difficulty)
    if language_code:
        query["language_code"] = language_code.strip()
    if question_type:
        query["type"] = question_type.strip().lower()

    rows = list(
        coll("question_bank")
        .find(query)
        .sort([("times_used", -1), ("id", -1)])
    )

    result: list[dict[str, Any]] = []
    for bq in rows:
        times_correct = int(bq.get("times_correct") or 0)
        times_wrong = int(bq.get("times_wrong") or 0)
        total_answers = times_correct + times_wrong
        result.append(
            {
                "id": bq["id"],
                "question_text": bq["question_text"],
                "type": bq["type"],
                "topic_name": bq.get("topic_name") or "",
                "language_code": bq.get("language_code") or "",
                "difficulty": bq["difficulty"],
                "created_at": bq.get("created_at"),
                "times_used": int(bq.get("times_used") or 0),
                "times_correct": times_correct,
                "times_wrong": times_wrong,
                "percent_correct": round(
                    (times_correct / total_answers * 100) if total_answers > 0 else 0.0,
                    2,
                ),
                "percent_wrong": round(
                    (times_wrong / total_answers * 100) if total_answers > 0 else 0.0,
                    2,
                ),
            }
        )
    return result


def get_bank_availability(
    topic_names: list[str],
    difficulty: str,
    n_requested: int,
    *,
    exclude_employee_id: str | None = None,
) -> dict[str, Any]:
    diff = normalize_bank_level(difficulty)
    names = [n.strip() for n in topic_names if n and n.strip()]

    if not names:
        return {
            "available": 0,
            "requested": n_requested,
            "shortage": n_requested,
            "per_topic": [],
        }

    excluded: set[int] = set()
    if exclude_employee_id:
        excluded = get_employee_mastered_bank_ids(exclude_employee_id)

    per_topic: list[dict[str, Any]] = []
    total_available = 0
    bank = coll("question_bank")

    for tname in names:
        candidates = list(
            bank.find({"topic_name": tname, "difficulty": diff})
        )
        usable = [c for c in candidates if int(c["id"]) not in excluded]
        count = len(usable)
        total_available += count
        per_topic.append({"topic_name": tname, "available": count})

    shortage = max(0, n_requested - total_available)
    return {
        "available": total_available,
        "requested": n_requested,
        "shortage": shortage,
        "per_topic": per_topic,
    }
