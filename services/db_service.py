"""
PostgreSQL persistence for assessments and submissions (replaces CSV layer).
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from services.database import get_session_factory
from services.ids import sanitize_client_id
from services.models import (
    Assessment,
    AssessmentAttempt,
    AssessmentQuestion,
    Language,
    Submission,
    Topic,
)

__all__ = [
    "sanitize_client_id",
    "register_assessment",
    "client_may_access_assessment",
    "get_client_for_assessment",
    "save_assessment_rows",
    "save_shared_assessment_rows",
    "read_questions_by_assessment",
    "get_assessment_language_code",
    "get_assessment_routing_flag",
    "get_assessment_metadata",
    "get_topic_modality_by_names",
    "list_assessments_summary",
    "delete_assessment",
    "list_all_submissions",
    "get_participant_in_browser_submissions",
    "save_submission_row",
]

# Field-length caps — must stay in sync with the ORM column definitions in models.py
_MAX_LANGUAGE_CODE = 32
_MAX_LANGUAGE_LABEL = 256
_MAX_TOPIC_NAME = 512
_MAX_TOPIC_NAME_STORED = 1024   # coercion limit for values already in the DB
_MAX_TOPIC_NAMES_PER_ASSESSMENT = 50
_MAX_TOPIC_NAMES_COERCE = 80    # upper bound when reading back from JSON column


def _session() -> Session:
    return get_session_factory()()


def register_assessment(assessment_id: str, safe_client_id: str) -> None:
    """Ensure registry row: set owner_client_id for an existing assessment."""
    with _session() as session:
        row = session.get(Assessment, assessment_id)
        if row:
            row.owner_client_id = safe_client_id
        else:
            session.add(
                Assessment(
                    assessment_id=assessment_id,
                    owner_client_id=safe_client_id,
                    topic_names=[],
                    created_at=_utc_now_iso(),
                )
            )
        session.commit()


def get_client_for_assessment(assessment_id: str) -> str | None:
    with _session() as session:
        row = session.get(Assessment, assessment_id)
        if not row:
            return None
        return row.owner_client_id


def client_may_access_assessment(assessment_id: str, client_id: str | None) -> bool:
    """
    If the assessment is shared (no owner), anyone may access.
    If it is client-scoped, a non-empty client_id must match the owner.
    Empty / missing client_id is only allowed for shared assessments.
    """
    owner = get_client_for_assessment(assessment_id)
    if owner is None:
        return True
    cid = (client_id or "").strip()
    if not cid:
        return False
    return owner == cid


def _normalize_language_code(language_code: str | None) -> str | None:
    s = (language_code or "").strip()
    return s[:_MAX_LANGUAGE_CODE] if s else None


def _normalize_language_label(language_label: str | None) -> str | None:
    s = (language_label or "").strip()
    return s[:_MAX_LANGUAGE_LABEL] if s else None


def _normalize_topic_names(names: list[str] | None) -> list[str]:
    if not names:
        return []
    out: list[str] = []
    for x in names:
        s = str(x).strip()
        if s:
            out.append(s[:_MAX_TOPIC_NAME])
        if len(out) >= _MAX_TOPIC_NAMES_PER_ASSESSMENT:
            break
    return out


def _coerce_stored_topic_names(raw: Any) -> list[str]:
    """Normalize JSON/list/tuple/string forms from Postgres / SQLAlchemy into title strings."""
    if raw is None:
        return []
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return []
        try:
            parsed = json.loads(s)
        except json.JSONDecodeError:
            return [s[:_MAX_TOPIC_NAME]]
        raw = parsed
    if isinstance(raw, dict):
        raw = raw.get("topics") or raw.get("names") or raw.get("topic_names") or []
    if isinstance(raw, (list, tuple)):
        return [
            str(x).strip()
            for x in raw
            if str(x).strip() and len(str(x).strip()) <= _MAX_TOPIC_NAME_STORED
        ][:_MAX_TOPIC_NAMES_COERCE]
    return []


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _created_at_sort_key(row: dict[str, Any]) -> tuple[int, str]:
    """
    Sort with newest created_at first; rows without created_at go last.
    """
    raw = (row.get("created_at") or "").strip()
    if not raw:
        return (0, "")
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return (1, dt.astimezone(timezone.utc).isoformat())
    except ValueError:
        return (0, raw)


def save_assessment_rows(
    assessment_id: str,
    rows: list[dict[str, Any]],
    client_id: str,
    *,
    language_code: str | None = None,
    language_label: str | None = None,
    topic_names: list[str] | None = None,
) -> None:
    """Persist questions scoped to a client (owner_client_id set)."""
    safe = sanitize_client_id(client_id)
    lang = _normalize_language_code(language_code)
    lbl = _normalize_language_label(language_label)
    topics = _normalize_topic_names(topic_names)
    with _session() as session:
        routing_flag = "pyodide"  # client-scoped assessments are always pyodide

        existing = session.get(Assessment, assessment_id)
        if existing:
            session.execute(
                delete(AssessmentQuestion).where(
                    AssessmentQuestion.assessment_id == assessment_id
                )
            )
            existing.owner_client_id = safe
            existing.routing_flag = routing_flag
            if language_code is not None:
                existing.language_code = lang
            if language_label is not None:
                existing.language_label = lbl
            if topic_names is not None:
                existing.topic_names = topics
        else:
            session.add(
                Assessment(
                    assessment_id=assessment_id,
                    owner_client_id=safe,
                    language_code=lang if language_code is not None else None,
                    language_label=lbl,
                    topic_names=topics,
                    routing_flag=routing_flag,
                    created_at=_utc_now_iso(),
                )
            )
        for row in rows:
            session.add(
                AssessmentQuestion(
                    assessment_id=assessment_id,
                    question_id=str(row["question_id"]),
                    question=row["question"],
                    type=row["type"],
                    options=row.get("options", "") or "",
                    correct_answer=row.get("correct_answer", "") or "",
                    topic_name=str(row.get("topic_name") or ""),
                    code_snippet=row.get("code_snippet") or None,
                )
            )
        session.commit()


def update_assessment_question(
    assessment_id: str,
    question_id: str,
    *,
    question: str | None = None,
    code_snippet: str | None = None,
    options: str | None = None,
    correct_answer: str | None = None,
) -> bool:
    """Partially update a single question row. Returns True if the row was found and updated."""
    with _session() as session:
        row = session.scalar(
            select(AssessmentQuestion).where(
                AssessmentQuestion.assessment_id == assessment_id,
                AssessmentQuestion.question_id == str(question_id),
            )
        )
        if not row:
            return False
        if question is not None:
            row.question = question.strip()
        if code_snippet is not None:
            row.code_snippet = code_snippet.strip() or None
        if options is not None:
            row.options = options
        if correct_answer is not None:
            row.correct_answer = correct_answer.strip()
        session.commit()
        return True


def get_topics_by_names(topic_names: list[str]):
    """Return Topic ORM rows matching the given names (used by assessment_service)."""
    names = [n.strip() for n in topic_names if n and str(n).strip()]
    if not names:
        return []
    with _session() as session:
        return session.scalars(select(Topic).where(Topic.name.in_(names))).all()


def save_shared_assessment_rows(
    assessment_id: str,
    rows: list[dict[str, Any]],
    *,
    routing_flag: str = "pyodide",
    language_code: str | None = None,
    language_label: str | None = None,
    topic_names: list[str] | None = None,
    is_timed: bool = False,
    duration_minutes: int | None = None,
    notebook_grace_minutes: int | None = None,
) -> None:
    """Shared assessment: owner_client_id is NULL (any client may access).

    ``routing_flag`` must be computed by the caller (assessment_service._compute_routing_flag)
    before persisting — this function is a pure persistence layer.
    """
    with _session() as session:
        existing = session.get(Assessment, assessment_id)
        lang = _normalize_language_code(language_code)
        lbl = _normalize_language_label(language_label)
        topics = _normalize_topic_names(
            topic_names if topic_names is not None else []
        )



        if existing:
            session.execute(
                delete(AssessmentQuestion).where(
                    AssessmentQuestion.assessment_id == assessment_id
                )
            )
            existing.owner_client_id = None
            existing.routing_flag = routing_flag
            if language_code is not None:
                existing.language_code = lang
            if language_label is not None:
                existing.language_label = lbl
            if topic_names is not None:
                existing.topic_names = topics
            existing.is_timed = is_timed
            existing.duration_minutes = duration_minutes if is_timed else None
            existing.notebook_grace_minutes = (
                notebook_grace_minutes if is_timed else None
            )
        else:
            session.add(
                Assessment(
                    assessment_id=assessment_id,
                    owner_client_id=None,
                    language_code=lang if language_code is not None else None,
                    language_label=lbl,
                    topic_names=topics,
                    routing_flag=routing_flag,
                    created_at=_utc_now_iso(),
                    is_timed=is_timed,
                    duration_minutes=duration_minutes if is_timed else None,
                    notebook_grace_minutes=(
                        notebook_grace_minutes if is_timed else None
                    ),
                )
            )
        for row in rows:
            session.add(
                AssessmentQuestion(
                    assessment_id=assessment_id,
                    question_id=str(row["question_id"]),
                    question=row["question"],
                    type=row["type"],
                    options=row.get("options", "") or "",
                    correct_answer=row.get("correct_answer", "") or "",
                    topic_name=str(row.get("topic_name") or ""),
                    code_snippet=row.get("code_snippet") or None,
                )
            )
        session.commit()


def read_questions_by_assessment(assessment_id: str) -> list[dict[str, Any]]:
    with _session() as session:
        rows = session.scalars(
            select(AssessmentQuestion)
            .where(AssessmentQuestion.assessment_id == assessment_id)
            .order_by(AssessmentQuestion.id)
        ).all()
        return [
            {
                "assessment_id": assessment_id,
                "question_id": r.question_id,
                "question": r.question,
                "type": r.type,
                "options": r.options or "",
                "correct_answer": r.correct_answer or "",
                "topic_name": r.topic_name or "",
                "code_snippet": r.code_snippet or "",
                "bank_question_id": r.bank_question_id,
                "difficulty": r.difficulty or "",
            }
            for r in rows
        ]


def get_assessment_language_code(assessment_id: str) -> str | None:
    """Catalog language `code` stored on the assessment row, if any."""
    with _session() as session:
        row = session.get(Assessment, assessment_id)
        if not row:
            return None
        return _normalize_language_code(row.language_code)


def get_assessment_routing_flag(assessment_id: str) -> str:
    """Routing flag stored on the assessment row, if any, defaulting to 'pyodide'."""
    with _session() as session:
        row = session.get(Assessment, assessment_id)
        if not row:
            return "pyodide"
        return row.routing_flag or "pyodide"


def get_topic_modality_by_names(topic_names: list[str]) -> dict[str, str]:
    """Map catalog topic name → modality ('pyodide' or 'jupyter')."""
    names = [n.strip() for n in topic_names if n and str(n).strip()]
    if not names:
        return {}
    with _session() as session:
        rows = session.scalars(select(Topic).where(Topic.name.in_(names))).all()
        return {r.name: (r.modality or "pyodide") for r in rows}


def get_topic_coding_editor_by_names(names: list[str]) -> dict[str, str | None]:
    """Map catalog topic name → coding_editor_language ('shell', 'powershell', or None)."""
    cleaned = [n.strip() for n in names if n and str(n).strip()]
    if not cleaned:
        return {}
    with _session() as session:
        rows = session.scalars(select(Topic).where(Topic.name.in_(cleaned))).all()
        out: dict[str, str | None] = {}
        for r in rows:
            cel = (r.coding_editor_language or "").strip().lower() or None
            if cel in ("shell", "powershell"):
                out[r.name] = cel
            else:
                out[r.name] = None
        return out


def get_assessment_metadata(assessment_id: str) -> dict[str, Any]:
    """Return language_code, routing_flag, topic_names, and jupyter_topic_names in one query."""
    with _session() as session:
        row = session.get(Assessment, assessment_id)
        if not row:
            return {
                "language_code": None,
                "routing_flag": "pyodide",
                "topic_names": [],
                "jupyter_topic_names": [],
                "is_timed": False,
                "duration_minutes": None,
                "notebook_grace_minutes": None,
            }
        topic_names = _coerce_stored_topic_names(row.topic_names)
        jupyter_topic_names: list[str] = []
        if topic_names:
            jupyter_topic_names = list(
                session.scalars(
                    select(Topic.name).where(
                        Topic.name.in_(topic_names),
                        Topic.modality == "jupyter",
                    )
                ).all()
            )
        return {
            "language_code": _normalize_language_code(row.language_code),
            "routing_flag": row.routing_flag or "pyodide",
            "topic_names": topic_names,
            "jupyter_topic_names": jupyter_topic_names,
            "is_timed": bool(row.is_timed),
            "duration_minutes": row.duration_minutes,
            "notebook_grace_minutes": row.notebook_grace_minutes,
        }


def list_assessments_summary() -> list[dict[str, Any]]:
    with _session() as session:
        assessments = session.scalars(select(Assessment)).all()
        langs = session.scalars(select(Language)).all()

        # Case-insensitive lookup: assessment may store catalog code with different casing
        lang_name_by_code_cf: dict[str, str] = {}
        for lg in langs:
            k = _normalize_language_code(lg.code)
            if k:
                lang_name_by_code_cf[k.casefold()] = (lg.name or "").strip()[:_MAX_LANGUAGE_LABEL] or k

        # Single GROUP BY query replaces N per-row COUNT(*) calls
        counts_rows = session.execute(
            select(
                AssessmentQuestion.assessment_id,
                func.count().label("n"),
            ).group_by(AssessmentQuestion.assessment_id)
        ).all()
        count_by_id: dict[str, int] = {r.assessment_id: int(r.n) for r in counts_rows}

        result: list[dict[str, Any]] = []
        for a in assessments:
            cid = a.owner_client_id or "common"
            source = "shared" if a.owner_client_id is None else "client"
            lc = _normalize_language_code(a.language_code)
            stored_label = (a.language_label or "").strip() or None
            catalog_name = lang_name_by_code_cf.get(lc.casefold()) if lc else None
            # Prefer catalog name; then stored UI label; fall back to code
            language_name = catalog_name or stored_label or (lc if lc else None)
            topics = _coerce_stored_topic_names(a.topic_names)
            result.append(
                {
                    "assessment_id": a.assessment_id,
                    "client_id": cid,
                    "question_count": count_by_id.get(a.assessment_id, 0),
                    "source": source,
                    "language_code": lc,
                    "language_label": stored_label,
                    "language_name": language_name,
                    "topic_names": topics,
                    "created_at": (a.created_at or "").strip() or None,
                    "routing_flag": a.routing_flag,
                    "is_timed": bool(a.is_timed),
                    "duration_minutes": a.duration_minutes,
                    "notebook_grace_minutes": a.notebook_grace_minutes,
                }
            )
        return sorted(
            result,
            key=lambda x: (_created_at_sort_key(x), x["assessment_id"]),
            reverse=True,
        )


def delete_assessment(assessment_id: str) -> None:
    """Remove assessment, its questions, and all submission rows for that assessment."""
    aid = assessment_id.strip()
    if not aid:
        raise ValueError("Assessment ID is required")
    with _session() as session:
        row = session.get(Assessment, aid)
        if not row:
            raise ValueError("Assessment not found")
        session.execute(delete(Submission).where(Submission.assessment_id == aid))
        session.execute(
            delete(AssessmentAttempt).where(AssessmentAttempt.assessment_id == aid)
        )
        session.delete(row)
        session.commit()


_NOTEBOOK_QUESTION_ID = "notebook"


def get_participant_in_browser_submissions(
    assessment_id: str,
    employee_id: str,
) -> list[dict[str, Any]]:
    """In-browser submission rows for one participant (excludes Jupyter notebook rows)."""
    from services.attempt_service import normalize_employee_id

    eid_norm = normalize_employee_id(employee_id)
    if not eid_norm:
        return []

    aid = assessment_id.strip()
    with _session() as session:
        rows = session.scalars(
            select(Submission)
            .where(
                Submission.assessment_id == aid,
                Submission.question_id != _NOTEBOOK_QUESTION_ID,
                Submission.routing_flag != "jupyter",
            )
            .order_by(Submission.id)
        ).all()

    out: list[dict[str, Any]] = []
    for r in rows:
        uid = r.user_id or ""
        part = uid.split("|", 1)[0].strip().casefold()
        if part != eid_norm:
            continue
        out.append(
            {
                "assessment_id": r.assessment_id,
                "user_id": r.user_id,
                "question_id": r.question_id,
                "user_answer": r.user_answer,
                "score": r.score,
                "feedback": r.feedback,
                "timestamp": r.timestamp,
                "routing_flag": r.routing_flag,
            }
        )
    return out


def list_all_submissions() -> list[dict[str, Any]]:
    with _session() as session:
        rows = session.scalars(
            select(Submission).order_by(Submission.timestamp.desc())
        ).all()
        out: list[dict[str, Any]] = []
        for r in rows:
            cid = r.submitter_client_id if r.submitter_client_id else "common"
            out.append(
                {
                    "assessment_id": r.assessment_id,
                    "user_id": r.user_id,
                    "question_id": r.question_id,
                    "user_answer": r.user_answer,
                    "score": r.score,
                    "feedback": r.feedback,
                    "timestamp": r.timestamp,
                    "client_id": cid,
                    "routing_flag": r.routing_flag,
                }
            )
        return out


def save_submission_row(
    assessment_id: str,
    user_id: str,
    question_id: str,
    user_answer: str,
    score: str,
    feedback: str,
    timestamp: str,
    *,
    submitter_client_id: str | None = None,
    routing_flag: str = "pyodide",
    raw_notebook: dict | None = None,
) -> None:
    with _session() as session:
        session.add(
            Submission(
                assessment_id=assessment_id,
                user_id=user_id,
                question_id=question_id,
                user_answer=user_answer,
                score=score,
                feedback=feedback,
                timestamp=timestamp,
                submitter_client_id=submitter_client_id,
                routing_flag=routing_flag,
                raw_notebook=raw_notebook,
            )
        )
        session.commit()

