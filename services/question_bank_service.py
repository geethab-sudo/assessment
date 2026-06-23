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

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from services.database import get_session_factory
from services.models import (
    Assessment,
    AssessmentQuestion,
    EmployeeQuestionMastery,
    QuestionBank,
    Submission,
)


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


def _session() -> Session:
    return get_session_factory()()


# ---------------------------------------------------------------------------
# Content hashing (deduplication key)
# ---------------------------------------------------------------------------

def _content_hash(qtype: str, topic_name: str, question_text: str) -> str:
    """SHA-256 of (type | topic | first 1000 chars of question text)."""
    payload = f"{qtype.strip().lower()}|{topic_name.strip()}|{question_text.strip()[:1000]}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Upsert questions into the bank (called after assessment confirm/create)
# ---------------------------------------------------------------------------

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

    with _session() as session:
        for row in rows:
            qtype = (row.get("type") or "").strip().lower()
            topic = (row.get("topic_name") or "").strip()
            qtext = (row.get("question") or "").strip()
            if not qtext or not qtype:
                continue

            ch = _content_hash(qtype, topic, qtext)

            existing = session.scalar(
                select(QuestionBank).where(QuestionBank.content_hash == ch)
            )
            if existing:
                existing.times_used = existing.times_used + 1
                hash_to_id[ch] = existing.id
            else:
                bank_row = QuestionBank(
                    content_hash=ch,
                    question_text=qtext,
                    type=qtype,
                    options=row.get("options", "") or "",
                    correct_answer=row.get("correct_answer", "") or "",
                    code_snippet=row.get("code_snippet") or None,
                    topic_name=topic,
                    language_code=lang,
                    difficulty=diff,
                    created_at=_utc_now_iso(),
                    times_used=1,
                    times_correct=0,
                    times_wrong=0,
                    sample_test_cases=row.get("sample_test_cases"),
                    coding_hint=row.get("coding_hint") or None,
                )
                session.add(bank_row)
                session.flush()  # assigns bank_row.id
                hash_to_id[ch] = bank_row.id

        session.commit()

    return hash_to_id


def _topic_name_for_bank_row(
    aq: AssessmentQuestion,
    assessment: Assessment | None,
) -> str:
    """Resolve catalog topic name for a legacy assessment question row."""
    topic = (aq.topic_name or "").strip()
    if topic:
        return topic
    if not assessment:
        return ""
    names = assessment.topic_names or []
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

    with _session() as session:
        aq_rows = session.scalars(
            select(AssessmentQuestion)
            .where(AssessmentQuestion.bank_question_id.is_(None))
            .order_by(AssessmentQuestion.id.asc())
        ).all()

        assessment_cache: dict[str, Assessment | None] = {}

        def _assessment_for(aq: AssessmentQuestion) -> Assessment | None:
            aid = aq.assessment_id
            if aid not in assessment_cache:
                assessment_cache[aid] = session.get(Assessment, aid)
            return assessment_cache[aid]

        for aq in aq_rows:
            qtype = (aq.type or "").strip().lower()
            qtext = (aq.question or "").strip()
            if not qtype or not qtext:
                continue

            assessment = _assessment_for(aq)
            topic = _topic_name_for_bank_row(aq, assessment)
            if not topic:
                continue

            level = infer_bank_level_from_topic(
                topic,
                explicit_difficulty=aq.difficulty,
            )
            lang = None
            if assessment and assessment.language_code:
                lang = (assessment.language_code or "").strip()[:32] or None

            ch = _content_hash(qtype, topic, qtext)
            existing = session.scalar(
                select(QuestionBank).where(QuestionBank.content_hash == ch)
            )
            if existing:
                existing.times_used = (existing.times_used or 0) + 1
                bank_id = existing.id
            else:
                bank_row = QuestionBank(
                    content_hash=ch,
                    question_text=qtext,
                    type=qtype,
                    options=aq.options or "",
                    correct_answer=aq.correct_answer or "",
                    code_snippet=aq.code_snippet or None,
                    topic_name=topic,
                    language_code=lang,
                    difficulty=level,
                    created_at=_utc_now_iso(),
                    times_used=1,
                    times_correct=0,
                    times_wrong=0,
                )
                session.add(bank_row)
                session.flush()
                bank_id = bank_row.id

            aq.bank_question_id = bank_id
            if not aq.difficulty:
                aq.difficulty = level
            linked += 1

        session.commit()

    return linked


# ---------------------------------------------------------------------------
# Link assessment_questions rows to their bank counterparts
# ---------------------------------------------------------------------------

def link_assessment_questions_to_bank(
    assessment_id: str,
    hash_to_bank_id: dict[str, int],
    level: str,
) -> None:
    """Set bank_question_id and difficulty on matching assessment_question rows."""
    if not hash_to_bank_id:
        return

    diff = normalize_bank_level(level)

    with _session() as session:
        aq_rows = session.scalars(
            select(AssessmentQuestion).where(
                AssessmentQuestion.assessment_id == assessment_id
            )
        ).all()

        for aq in aq_rows:
            qtype = (aq.type or "").strip().lower()
            topic = (aq.topic_name or "").strip()
            qtext = (aq.question or "").strip()
            ch = _content_hash(qtype, topic, qtext)
            bank_id = hash_to_bank_id.get(ch)
            if bank_id is not None:
                aq.bank_question_id = bank_id
                aq.difficulty = diff

        session.commit()


# ---------------------------------------------------------------------------
# Stats counters (atomic updates)
# ---------------------------------------------------------------------------

def increment_question_usage(bank_question_id: int) -> None:
    """Atomically increment times_used for a bank question."""
    with _session() as session:
        session.execute(
            update(QuestionBank)
            .where(QuestionBank.id == bank_question_id)
            .values(times_used=QuestionBank.times_used + 1)
        )
        session.commit()


def record_question_outcome(bank_question_id: int | None, correct: bool) -> None:
    """Atomically increment times_correct or times_wrong for a bank question."""
    if bank_question_id is None:
        return

    with _session() as session:
        if correct:
            session.execute(
                update(QuestionBank)
                .where(QuestionBank.id == bank_question_id)
                .values(times_correct=QuestionBank.times_correct + 1)
            )
        else:
            session.execute(
                update(QuestionBank)
                .where(QuestionBank.id == bank_question_id)
                .values(times_wrong=QuestionBank.times_wrong + 1)
            )
        session.commit()


def record_employee_question_mastery(
    employee_id: str,
    bank_question_id: int | None,
) -> None:
    """
    Persist that this employee mastered a bank question (answered correctly).

    Idempotent: duplicate (employee_id, bank_question_id) pairs are ignored.
    """
    from services.attempt_service import normalize_employee_id

    if bank_question_id is None:
        return
    eid = normalize_employee_id(employee_id)
    if not eid:
        return

    with _session() as session:
        existing = session.scalar(
            select(EmployeeQuestionMastery.id).where(
                EmployeeQuestionMastery.employee_id == eid,
                EmployeeQuestionMastery.bank_question_id == bank_question_id,
            )
        )
        if existing is not None:
            return
        session.add(
            EmployeeQuestionMastery(
                employee_id=eid,
                bank_question_id=bank_question_id,
                mastered_at=_utc_now_iso(),
            )
        )
        session.commit()


def backfill_employee_mastery_from_submissions() -> int:
    """
    Populate ``employee_question_mastery`` from historical correct submissions.

    Returns the number of new mastery rows inserted.
    """
    from services.attempt_service import (
        normalize_employee_id,
        parse_employee_id_from_user_label,
    )

    inserted = 0
    with _session() as session:
        subs = session.scalars(
            select(Submission).where(Submission.question_id != "notebook")
        ).all()

        for sub in subs:
            eid = normalize_employee_id(
                parse_employee_id_from_user_label(sub.user_id or "")
            )
            if not eid:
                continue

            aq = session.scalar(
                select(AssessmentQuestion).where(
                    AssessmentQuestion.assessment_id == sub.assessment_id,
                    AssessmentQuestion.question_id == sub.question_id,
                )
            )
            if not aq or aq.bank_question_id is None:
                continue

            if not _submission_indicates_mastered(
                aq.type,
                sub.user_answer,
                aq.correct_answer,
                sub.score,
            ):
                continue

            exists = session.scalar(
                select(EmployeeQuestionMastery.id).where(
                    EmployeeQuestionMastery.employee_id == eid,
                    EmployeeQuestionMastery.bank_question_id == aq.bank_question_id,
                )
            )
            if exists is not None:
                continue

            session.add(
                EmployeeQuestionMastery(
                    employee_id=eid,
                    bank_question_id=aq.bank_question_id,
                    mastered_at=sub.timestamp or _utc_now_iso(),
                )
            )
            inserted += 1

        session.commit()
    return inserted


# ---------------------------------------------------------------------------
# Employee exclusion — mastered questions only
# ---------------------------------------------------------------------------

def _submission_indicates_mastered(
    qtype: str,
    user_answer: str,
    correct_answer: str,
    score_text: str,
) -> bool:
    """True when the participant answered correctly (MCQ match or score ≥ 70)."""
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
    """
    Return bank question IDs this employee has mastered (answered correctly).

    Reads the persistent ``employee_question_mastery`` table (not recomputed from
    submissions). Rows are added by ``record_employee_question_mastery`` on submit.
    """
    from services.attempt_service import normalize_employee_id

    eid = normalize_employee_id(employee_id)
    if not eid:
        return set()

    with _session() as session:
        rows = session.scalars(
            select(EmployeeQuestionMastery.bank_question_id).where(
                EmployeeQuestionMastery.employee_id == eid
            )
        ).all()
        return set(rows)


# ---------------------------------------------------------------------------
# Find reusable questions from the bank
# ---------------------------------------------------------------------------

def find_bank_questions(
    topic_names: list[str],
    difficulty: str,
    n_needed: int,
    *,
    question_type: str | None = None,
    exclude_bank_ids: set[int] | None = None,
    exclude_employee_id: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """
    Find up to n_needed reusable questions from the bank.

    Returns (found_list, shortage_count) where shortage_count = max(0, n_needed - len(found)).
    Questions **mastered** by exclude_employee_id are excluded; wrong answers may repeat.
    """
    if n_needed <= 0 or not topic_names:
        return [], max(0, n_needed)

    diff = normalize_bank_level(difficulty)
    qtype_filter = (question_type or "").strip().lower() or None
    names = [n.strip() for n in topic_names if n and n.strip()]
    if not names:
        return [], n_needed

    # Build exclusion set
    all_excluded: set[int] = set(exclude_bank_ids or set())
    if exclude_employee_id:
        all_excluded |= get_employee_mastered_bank_ids(exclude_employee_id)

    with _session() as session:
        query = (
            select(QuestionBank)
            .where(
                QuestionBank.topic_name.in_(names),
                QuestionBank.difficulty == diff,
            )
            .order_by(
                QuestionBank.times_used.asc(),
                QuestionBank.id.asc(),
            )
        )
        if qtype_filter:
            query = query.where(QuestionBank.type == qtype_filter)

        candidates = session.scalars(query).all()

        found: list[dict[str, Any]] = []
        for bq in candidates:
            if bq.id in all_excluded:
                continue
            if len(found) >= n_needed:
                break
            found.append({
                "bank_question_id": bq.id,
                "question": bq.question_text,
                "type": bq.type,
                "options": bq.options or "",
                "correct_answer": bq.correct_answer or "",
                "topic_name": bq.topic_name or "",
                "code_snippet": bq.code_snippet or "",
                "difficulty": bq.difficulty,
                "sample_test_cases": bq.sample_test_cases,
                "coding_hint": bq.coding_hint or "",
            })

    shortage = max(0, n_needed - len(found))
    return found, shortage


# ---------------------------------------------------------------------------
# Bank browsing / stats (admin API)
# ---------------------------------------------------------------------------

def get_bank_stats(
    *,
    topic_name: str | None = None,
    difficulty: str | None = None,
    language_code: str | None = None,
    question_type: str | None = None,
) -> list[dict[str, Any]]:
    """Return bank questions with stats, filtered by optional criteria."""
    with _session() as session:
        query = select(QuestionBank).order_by(
            QuestionBank.times_used.desc(),
            QuestionBank.id.desc(),
        )

        if topic_name:
            query = query.where(QuestionBank.topic_name == topic_name.strip())
        if difficulty:
            query = query.where(
                QuestionBank.difficulty == normalize_bank_level(difficulty)
            )
        if language_code:
            query = query.where(QuestionBank.language_code == language_code.strip())
        if question_type:
            query = query.where(QuestionBank.type == question_type.strip().lower())

        rows = session.scalars(query).all()

        result: list[dict[str, Any]] = []
        for bq in rows:
            total_answers = bq.times_correct + bq.times_wrong
            result.append({
                "id": bq.id,
                "question_text": bq.question_text,
                "type": bq.type,
                "topic_name": bq.topic_name or "",
                "language_code": bq.language_code or "",
                "difficulty": bq.difficulty,
                "created_at": bq.created_at,
                "times_used": bq.times_used,
                "times_correct": bq.times_correct,
                "times_wrong": bq.times_wrong,
                "percent_correct": round(
                    (bq.times_correct / total_answers * 100) if total_answers > 0 else 0.0, 2
                ),
                "percent_wrong": round(
                    (bq.times_wrong / total_answers * 100) if total_answers > 0 else 0.0, 2
                ),
            })
        return result


def get_bank_availability(
    topic_names: list[str],
    difficulty: str,
    n_requested: int,
    *,
    exclude_employee_id: str | None = None,
) -> dict[str, Any]:
    """
    Check how many bank questions are available for the given topics/difficulty.

    Returns availability info including per-topic breakdown and shortfall.
    """
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

    with _session() as session:
        per_topic: list[dict[str, Any]] = []
        total_available = 0

        for tname in names:
            candidates = session.scalars(
                select(QuestionBank).where(
                    QuestionBank.topic_name == tname,
                    QuestionBank.difficulty == diff,
                )
            ).all()

            usable = [c for c in candidates if c.id not in excluded]
            count = len(usable)
            total_available += count
            per_topic.append({
                "topic_name": tname,
                "available": count,
            })

    shortage = max(0, n_requested - total_available)
    return {
        "available": total_available,
        "requested": n_requested,
        "shortage": shortage,
        "per_topic": per_topic,
    }
