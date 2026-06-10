"""
Question Bank — canonical reusable question store with analytics counters.

Every confirmed assessment question is automatically upserted here.
Questions can be recycled across assessments while excluding questions
a specific employee has already seen.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from services.database import get_session_factory
from services.models import (
    AssessmentQuestion,
    QuestionBank,
    Submission,
)


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
    difficulty: str,
    language_code: str | None = None,
) -> dict[str, int]:
    """
    Upsert question rows into the bank. Returns mapping of content_hash → bank id.

    Idempotent: existing questions (by content hash) are not duplicated.
    New questions are inserted; existing ones have their times_used incremented.
    """
    if not rows:
        return {}

    diff = difficulty.strip().lower()
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
                )
                session.add(bank_row)
                session.flush()  # assigns bank_row.id
                hash_to_id[ch] = bank_row.id

        session.commit()

    return hash_to_id


# ---------------------------------------------------------------------------
# Link assessment_questions rows to their bank counterparts
# ---------------------------------------------------------------------------

def link_assessment_questions_to_bank(
    assessment_id: str,
    hash_to_bank_id: dict[str, int],
    difficulty: str,
) -> None:
    """Set bank_question_id and difficulty on matching assessment_question rows."""
    if not hash_to_bank_id:
        return

    diff = difficulty.strip().lower()

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


# ---------------------------------------------------------------------------
# Employee deduplication — questions already seen
# ---------------------------------------------------------------------------

def get_employee_seen_bank_ids(employee_id: str) -> set[int]:
    """
    Return all bank question IDs this employee has already answered.

    Looks up submissions by employee_id prefix (matches the 'E1001 | Name' format),
    then resolves question_id → assessment_questions.bank_question_id.
    """
    from services.attempt_service import normalize_employee_id

    eid_norm = normalize_employee_id(employee_id)
    if not eid_norm:
        return set()

    with _session() as session:
        # Find all submissions for this employee
        subs = session.scalars(
            select(Submission).where(
                Submission.question_id != "notebook"
            )
        ).all()

        # Filter by employee id prefix match
        relevant_assessment_qids: list[tuple[str, str]] = []
        for s in subs:
            uid = s.user_id or ""
            part = uid.split("|", 1)[0].strip().casefold()
            if part == eid_norm:
                relevant_assessment_qids.append((s.assessment_id, s.question_id))

        if not relevant_assessment_qids:
            return set()

        # Resolve to bank_question_ids
        seen: set[int] = set()
        for aid, qid in relevant_assessment_qids:
            aq = session.scalar(
                select(AssessmentQuestion).where(
                    AssessmentQuestion.assessment_id == aid,
                    AssessmentQuestion.question_id == qid,
                )
            )
            if aq and aq.bank_question_id is not None:
                seen.add(aq.bank_question_id)

        return seen


# ---------------------------------------------------------------------------
# Find reusable questions from the bank
# ---------------------------------------------------------------------------

def find_bank_questions(
    topic_names: list[str],
    difficulty: str,
    n_needed: int,
    *,
    exclude_bank_ids: set[int] | None = None,
    exclude_employee_id: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """
    Find up to n_needed reusable questions from the bank.

    Returns (found_list, shortage_count) where shortage_count = max(0, n_needed - len(found)).
    Questions already answered by exclude_employee_id are excluded.
    """
    if n_needed <= 0 or not topic_names:
        return [], max(0, n_needed)

    diff = difficulty.strip().lower()
    names = [n.strip() for n in topic_names if n and n.strip()]
    if not names:
        return [], n_needed

    # Build exclusion set
    all_excluded: set[int] = set(exclude_bank_ids or set())
    if exclude_employee_id:
        all_excluded |= get_employee_seen_bank_ids(exclude_employee_id)

    with _session() as session:
        query = (
            select(QuestionBank)
            .where(
                QuestionBank.topic_name.in_(names),
                QuestionBank.difficulty == diff,
            )
            .order_by(
                # Prefer less-used questions for variety
                QuestionBank.times_used.asc(),
                QuestionBank.id.asc(),
            )
        )

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
            query = query.where(QuestionBank.difficulty == difficulty.strip().lower())
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
    diff = difficulty.strip().lower()
    names = [n.strip() for n in topic_names if n and n.strip()]

    if not names:
        return {
            "available": 0,
            "requested": n_requested,
            "shortage": n_requested,
            "per_topic": [],
        }

    # Exclusions
    excluded: set[int] = set()
    if exclude_employee_id:
        excluded = get_employee_seen_bank_ids(exclude_employee_id)

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
