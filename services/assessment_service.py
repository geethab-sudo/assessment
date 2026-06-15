"""
Orchestrates LLM calls and database reads/writes for assessments and submissions.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from services.ids import generate_assessment_id
from typing import Any

from services import db_service
from services import question_bank_service
from services import attempt_service
from services.database import get_session_factory
from services.llm_service import evaluate_answers, generate_questions
from services.models import Assessment
from services.notebook_plan_service import (
    derive_per_topic_config,
    jupyter_topic_names_from_list,
    notebook_plan_for_assessment,
    notebook_plan_from_rows,
    resolve_question_modality,
    validate_notebook_plan_after_generation,
)
from services.question_stem import (
    format_question_for_grading,
    prettify_inline_code,
    split_stem_for_display,
)
from services.shuffle_service import apply_participant_shuffle


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LEVEL_TO_DIFFICULTY = {
    "beginner": "easy",
    "intermediate": "medium",
    "advanced": "hard",
}

SCORE_CORRECT_THRESHOLD = 70.0

_TYPE_ORDER = ("mcq", "coding", "subjective")

_SHELL_CODING_HINT = (
    "\n\nCoding questions for this topic: expect terminal/shell answers "
    "(bash on Unix/macOS, e.g. `python3 -m venv .venv` and `source .venv/bin/activate`, "
    "or PowerShell on Windows, e.g. `python -m venv .venv` and `.venv\\Scripts\\Activate.ps1`). "
    "Do not ask participants to write Python scripts for venv setup unless the task explicitly requires it."
)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _upsert_to_bank(
    assessment_id: str,
    rows: list[dict[str, Any]],
    level: str,
    language_code: str | None = None,
) -> None:
    """Upsert newly generated/confirmed questions into the reusable bank."""
    bank_level = level.strip().lower()
    hash_to_id = question_bank_service.add_questions_to_bank(rows, bank_level, language_code)
    question_bank_service.link_assessment_questions_to_bank(
        assessment_id, hash_to_id, bank_level
    )


def _options_for_csv(options: Any) -> str:
    """Serialize options list/dict to a JSON string for storage."""
    if options is None:
        return ""
    if isinstance(options, str):
        return options
    try:
        return json.dumps(options, ensure_ascii=False)
    except (TypeError, ValueError):
        return ""


def _is_answer_correct(
    qtype: str,
    user_text: str,
    correct_answer: str,
    score: float,
) -> bool:
    """MCQ: match stored correct answer text. Other types: score meets threshold."""
    if qtype == "mcq":
        return (
            user_text.strip().casefold() == (correct_answer or "").strip().casefold()
        )
    return score >= SCORE_CORRECT_THRESHOLD


def _types_and_counts_from_rows(
    rows: list[dict[str, Any]],
) -> tuple[list[str], dict[str, int]]:
    counts: dict[str, int] = {}
    for r in rows:
        qtype = (r.get("type") or "").strip().lower()
        if qtype:
            counts[qtype] = counts.get(qtype, 0) + 1
    types = [t for t in _TYPE_ORDER if t in counts]
    types.extend(sorted(t for t in counts if t not in _TYPE_ORDER))
    return types, counts


def _row_from_question(q: dict[str, Any], question_id: Any, topic_name: str) -> dict[str, Any]:
    """Normalise a single LLM question dict into a DB-ready row dict."""
    return {
        "question_id": str(question_id),
        "question": q["question"],
        "type": q["type"],
        "options": _options_for_csv(q.get("options") or []),
        "correct_answer": q.get("answer", ""),
        "topic_name": topic_name,
        "code_snippet": q.get("code_snippet") or "",
    }


# ---------------------------------------------------------------------------
# LLM topic string builder (queries catalog for reference docs)
# ---------------------------------------------------------------------------

def _build_per_topic_strings(topic_names: list[str]) -> dict[str, str]:
    """Return LLM topic strings for each catalog topic name (with reference docs)."""
    from sqlalchemy import select
    from services.models import Topic

    try:
        rows = db_service.get_topics_by_names(topic_names)
        by_name = {r.name: r for r in rows}
    except Exception:
        by_name = {}

    result: dict[str, str] = {}
    for tname in topic_names:
        row = by_name.get(tname)
        text = tname
        if row:
            docs = row.related_documents or []
            if docs:
                lines = []
                for d in docs:
                    title = (d.get("title") or "").strip() or "Reference"
                    url = (d.get("url") or "").strip()
                    path = (d.get("path") or "").strip()
                    if url:
                        lines.append(f"- {title}: {url}")
                    elif path:
                        lines.append(f"- {title}: {path}")
                    else:
                        lines.append(f"- {title}")
                text = f"{tname}\n\nContext (reference materials):\n" + "\n".join(lines)
            cel = (row.coding_editor_language or "").strip().lower()
            if cel in ("shell", "powershell"):
                text += _SHELL_CODING_HINT
        result[tname] = text
    return result


# ---------------------------------------------------------------------------
# Row generation helpers (one LLM call per topic, or single legacy call)
# ---------------------------------------------------------------------------

def _generate_rows_per_topic(
    assessment_id: str,
    catalog_topic_names: list[str],
    topic_strings: dict[str, str],
    difficulty: str,
    types: list[str],
    effective_per_topic: dict[str, dict[str, int]],
) -> list[dict[str, Any]]:
    """One LLM call per topic so questions are tagged with their topic_name."""
    rows: list[dict[str, Any]] = []
    global_q_id = 1
    for tname in catalog_topic_names:
        cfg = effective_per_topic.get(tname) or {}
        t_types = [t for t in types if cfg.get(t, 0) > 0]
        t_counts = {t: cfg[t] for t in t_types}
        if not t_types:
            continue
        t_questions = generate_questions(
            topic_strings.get(tname, tname),
            difficulty,
            t_types,
            questions_per_type=t_counts,
            assessment_id=f"{assessment_id}-{tname[:32]}",
        )
        for q in t_questions:
            rows.append(_row_from_question(q, global_q_id, tname))
            global_q_id += 1
    return rows


def _generate_rows_legacy(
    assessment_id: str,
    topic: str,
    difficulty: str,
    types: list[str],
    questions_per_type: dict[str, int],
) -> list[dict[str, Any]]:
    """Single LLM call for custom-topic or no-catalog-topic generations."""
    if set(types) != set(questions_per_type.keys()):
        raise ValueError("types and questions_per_type keys must match")
    questions = generate_questions(
        topic,
        difficulty,
        types,
        questions_per_type=questions_per_type,
        assessment_id=assessment_id,
    )
    return [
        _row_from_question(q, q.get("id"), "")
        for q in questions
    ]


# ---------------------------------------------------------------------------
# Routing flag (single source of truth — used before DB write)
# ---------------------------------------------------------------------------

def _compute_routing_flag(catalog_topic_names: list[str]) -> str:
    """Derive routing_flag from catalog topic modalities. Called before persisting."""
    if not catalog_topic_names:
        return "pyodide"
    jupyter_topics = jupyter_topic_names_from_list(catalog_topic_names)
    has_jupyter = bool(jupyter_topics)
    has_other = any(t not in set(jupyter_topics) for t in catalog_topic_names)
    if has_jupyter and has_other:
        return "mixed"
    if has_jupyter:
        return "jupyter"
    return "pyodide"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def preview_questions(
    topic: str,
    level: str,
    types: list[str],
    questions_per_type: dict[str, int],
    *,
    topic_names: list[str] | None = None,
    per_topic_config: dict[str, dict[str, int]] | None = None,
) -> dict[str, Any]:
    """Generate questions via LLM and return them for admin review — nothing is written to the DB.

    The returned dict contains the full question list (with correct_answer exposed for the
    admin) plus the metadata needed to call confirm_assessment() after editing.
    """
    difficulty = LEVEL_TO_DIFFICULTY.get(level.strip().lower())
    if not difficulty:
        raise ValueError("level must be one of: beginner, intermediate, advanced")

    # Use a throw-away assessment_id for LLM variation seeding only (never persisted)
    preview_id = str(uuid.uuid4())

    catalog_topic_names = [
        n.strip() for n in (topic_names or []) if n and str(n).strip()
    ]
    effective_per_topic: dict[str, dict[str, int]] | None = None
    if catalog_topic_names:
        effective_per_topic = (
            per_topic_config
            if per_topic_config
            else derive_per_topic_config(catalog_topic_names, types, questions_per_type)
        )

    if effective_per_topic and catalog_topic_names:
        topic_strings = _build_per_topic_strings(catalog_topic_names)
        rows = _generate_rows_per_topic(
            preview_id, catalog_topic_names, topic_strings, difficulty, types, effective_per_topic
        )
    else:
        rows = _generate_rows_legacy(preview_id, topic, difficulty, types, questions_per_type)

    routing_flag = _compute_routing_flag(catalog_topic_names)

    # Expose correct_answer and code_snippet so the admin can review and edit them
    questions_for_review: list[dict[str, Any]] = []
    for r in rows:
        raw_opts = r.get("options") or ""
        options = _parse_options(raw_opts) if raw_opts else []
        questions_for_review.append({
            "question_id": r["question_id"],
            "type": r["type"],
            "question": r["question"],
            "code_snippet": r.get("code_snippet") or "",
            "options": options,
            "correct_answer": r.get("correct_answer") or "",
            "topic_name": r.get("topic_name") or "",
        })

    return {
        "questions": questions_for_review,
        "meta": {
            "topic": topic,
            "level": level.strip().lower(),
            "difficulty": difficulty,
            "catalog_topic_names": catalog_topic_names,
            "routing_flag": routing_flag,
        },
    }


def confirm_assessment(
    questions: list[dict[str, Any]],
    *,
    topic: str,
    level: str,
    language_code: str | None = None,
    language_label: str | None = None,
    topic_names: list[str] | None = None,
    per_topic_config: dict[str, dict[str, int]] | None = None,
    is_timed: bool = False,
    duration_minutes: int | None = None,
    notebook_grace_minutes: int | None = None,
) -> dict[str, Any]:
    """Persist an admin-reviewed (and possibly edited) question list to the DB.

    Accepts the same question shape returned by preview_questions(), normalises
    it, then delegates to the same DB write path used by create_assessment().
    """
    difficulty = LEVEL_TO_DIFFICULTY.get(level.strip().lower())
    if not difficulty:
        raise ValueError("level must be one of: beginner, intermediate, advanced")

    assessment_id = generate_assessment_id()
    dur, grace = attempt_service.validate_timed_config(
        is_timed, duration_minutes, notebook_grace_minutes
    )

    catalog_topic_names = [
        n.strip() for n in (topic_names or []) if n and str(n).strip()
    ]

    # Re-derive per_topic_config from the edited question list so counts are accurate
    effective_per_topic: dict[str, dict[str, int]] = {}
    if catalog_topic_names and per_topic_config:
        effective_per_topic = per_topic_config
    elif catalog_topic_names:
        for q in questions:
            tname = (q.get("topic_name") or "").strip()
            qtype = (q.get("type") or "").strip().lower()
            if tname and qtype:
                effective_per_topic.setdefault(tname, {})
                effective_per_topic[tname][qtype] = effective_per_topic[tname].get(qtype, 0) + 1

    rows: list[dict[str, Any]] = [
        {
            "question_id": str(i + 1),
            "question": (q.get("question") or "").strip(),
            "type": (q.get("type") or "").strip().lower(),
            "options": _options_for_csv(q.get("options") or []),
            "correct_answer": (q.get("correct_answer") or "").strip(),
            "topic_name": (q.get("topic_name") or "").strip(),
            "code_snippet": (q.get("code_snippet") or "").strip(),
        }
        for i, q in enumerate(questions)
    ]

    routing_flag = _compute_routing_flag(catalog_topic_names)

    plan = notebook_plan_from_rows(
        rows,
        topic_names=catalog_topic_names,
        per_topic_config=effective_per_topic,
        routing_flag=routing_flag,
    )
    validate_notebook_plan_after_generation(plan)

    db_service.save_shared_assessment_rows(
        assessment_id,
        rows,
        routing_flag=routing_flag,
        language_code=language_code,
        language_label=language_label,
        topic_names=topic_names if topic_names is not None else [],
        is_timed=is_timed,
        duration_minutes=dur,
        notebook_grace_minutes=grace,
    )

    _upsert_to_bank(assessment_id, rows, level.strip().lower(), language_code)

    types, questions_per_type = _types_and_counts_from_rows(rows)

    return {
        "assessment_id": assessment_id,
        "topic": topic,
        "level": level.strip().lower(),
        "difficulty": difficulty,
        "types": types,
        "questions_per_type": questions_per_type,
        "question_count": len(rows),
        "language_code": (language_code or "").strip()[:32] or None,
        "language_label": (language_label or "").strip()[:256] or None,
        "topic_names": catalog_topic_names,
        "notebook_expected": plan["notebook_expected"],
        "notebook_ready": plan["notebook_ready"],
        "expected_notebook_coding_count": plan["expected_notebook_coding_count"],
        "actual_notebook_coding_count": plan["actual_notebook_coding_count"],
        "is_timed": is_timed,
        "duration_minutes": dur,
        "notebook_grace_minutes": grace,
    }


def create_assessment(
    topic: str,
    level: str,
    types: list[str],
    questions_per_type: dict[str, int],
    *,
    language_code: str | None = None,
    language_label: str | None = None,
    topic_names: list[str] | None = None,
    per_topic_config: dict[str, dict[str, int]] | None = None,
    is_timed: bool = False,
    duration_minutes: int | None = None,
    notebook_grace_minutes: int | None = None,
) -> dict[str, Any]:
    """Generate questions via LLM and persist (shared assessment in PostgreSQL)."""
    difficulty = LEVEL_TO_DIFFICULTY.get(level.strip().lower())
    if not difficulty:
        raise ValueError("level must be one of: beginner, intermediate, advanced")

    assessment_id = generate_assessment_id()
    dur, grace = attempt_service.validate_timed_config(
        is_timed, duration_minutes, notebook_grace_minutes
    )

    catalog_topic_names = [
        n.strip() for n in (topic_names or []) if n and str(n).strip()
    ]

    # Determine effective per-topic config (explicit or auto-derived)
    effective_per_topic: dict[str, dict[str, int]] | None = None
    if catalog_topic_names:
        effective_per_topic = (
            per_topic_config
            if per_topic_config
            else derive_per_topic_config(catalog_topic_names, types, questions_per_type)
        )

    # Generate question rows
    if effective_per_topic and catalog_topic_names:
        topic_strings = _build_per_topic_strings(catalog_topic_names)
        rows = _generate_rows_per_topic(
            assessment_id, catalog_topic_names, topic_strings, difficulty, types, effective_per_topic
        )
    else:
        rows = _generate_rows_legacy(assessment_id, topic, difficulty, types, questions_per_type)

    # Routing flag computed here once — passed to db_service (no re-computation there)
    routing_flag = _compute_routing_flag(catalog_topic_names)

    plan = notebook_plan_from_rows(
        rows,
        topic_names=catalog_topic_names,
        per_topic_config=effective_per_topic or {},
        routing_flag=routing_flag,
    )
    validate_notebook_plan_after_generation(plan)

    db_service.save_shared_assessment_rows(
        assessment_id,
        rows,
        routing_flag=routing_flag,
        language_code=language_code,
        language_label=language_label,
        topic_names=topic_names if topic_names is not None else [],
        is_timed=is_timed,
        duration_minutes=dur,
        notebook_grace_minutes=grace,
    )

    _upsert_to_bank(assessment_id, rows, level.strip().lower(), language_code)

    return {
        "assessment_id": assessment_id,
        "topic": topic,
        "level": level.strip().lower(),
        "difficulty": difficulty,
        "types": types,
        "questions_per_type": questions_per_type,
        "question_count": len(rows),
        "language_code": (language_code or "").strip()[:32] or None,
        "language_label": (language_label or "").strip()[:256] or None,
        "topic_names": catalog_topic_names,
        "notebook_expected": plan["notebook_expected"],
        "notebook_ready": plan["notebook_ready"],
        "expected_notebook_coding_count": plan["expected_notebook_coding_count"],
        "actual_notebook_coding_count": plan["actual_notebook_coding_count"],
        "is_timed": is_timed,
        "duration_minutes": dur,
        "notebook_grace_minutes": grace,
    }


def get_notebook_template_questions(assessment_id: str) -> list[dict[str, Any]]:
    """
    Coding questions for the downloadable .ipynb (jupyter-modality only).
    """
    meta = db_service.get_assessment_metadata(assessment_id)
    rows = db_service.read_questions_by_assessment(assessment_id)
    jupyter_topics = set(meta.get("jupyter_topic_names") or [])
    routing_flag = meta.get("routing_flag") or "pyodide"

    topic_names_on_questions = list(
        dict.fromkeys((r.get("topic_name") or "").strip() for r in rows if r.get("topic_name"))
    )
    modality_by_name = db_service.get_topic_modality_by_names(topic_names_on_questions)

    notebook_questions: list[dict[str, Any]] = []
    for r in rows:
        if (r.get("type") or "").lower() != "coding":
            continue
        tname = (r.get("topic_name") or "").strip()
        if resolve_question_modality(tname, jupyter_topics, modality_by_name) == "jupyter":
            notebook_questions.append({
                "question_id": r.get("question_id"),
                "question": r.get("question", ""),
                "topic_name": tname,
            })

    # Fallback: pure jupyter assessment without modality tags
    if not notebook_questions and routing_flag == "jupyter":
        for r in rows:
            if (r.get("type") or "").lower() == "coding":
                notebook_questions.append({
                    "question_id": r.get("question_id"),
                    "question": r.get("question", ""),
                    "topic_name": r.get("topic_name") or "",
                })

    return notebook_questions


def build_notebook_template(questions: list[dict[str, Any]], assessment_id: str) -> dict[str, Any]:
    """Build a .ipynb-compatible dict from a list of question dicts."""
    cells = []
    for i, q in enumerate(questions):
        cells.append({
            "cell_type": "markdown",
            "metadata": {},
            "source": [f"# Question {i + 1}\n", f"{q['question']}\n"],
        })
        cells.append({
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [],
        })
    return {
        "cells": cells,
        "metadata": {"language_info": {"name": "python"}},
        "nbformat": 4,
        "nbformat_minor": 2,
    }


def get_assessment_for_user(
    assessment_id: str,
    *,
    employee_id: str | None = None,
) -> dict[str, Any]:
    """
    Return assessment metadata and questions without revealing correct answers.

    When ``employee_id`` is provided, question order and MCQ option order are
    shuffled deterministically for that participant (assessment_id + employee_id).
    """
    meta = db_service.get_assessment_metadata(assessment_id)
    rows = db_service.read_questions_by_assessment(assessment_id)
    plan = notebook_plan_for_assessment(assessment_id)
    notebook_fields = {
        "notebook_expected": plan["notebook_expected"],
        "notebook_ready": plan["notebook_ready"],
        "expected_notebook_coding_count": plan["expected_notebook_coding_count"],
        "actual_notebook_coding_count": plan["actual_notebook_coding_count"],
    }

    base_out: dict[str, Any] = {
        "assessment_id": assessment_id,
        "language_code": meta["language_code"],
        "routing_flag": meta["routing_flag"],
        "topic_names": meta["topic_names"],
        "jupyter_topic_names": meta["jupyter_topic_names"],
        "is_timed": meta.get("is_timed", False),
        "duration_minutes": meta.get("duration_minutes"),
        "notebook_grace_minutes": meta.get("notebook_grace_minutes"),
        "already_submitted": False,
        "timer": None,
        **notebook_fields,
    }

    if not rows:
        return {**base_out, "questions": [], "found": False}

    questions_out = _build_questions_for_user(rows, meta)

    if employee_id and employee_id.strip():
        questions_out = apply_participant_shuffle(
            assessment_id, employee_id.strip(), questions_out
        )

    out = {**base_out, "questions": questions_out, "found": True}

    if meta.get("is_timed") and employee_id and employee_id.strip():
        out = _apply_timed_state(out, assessment_id, employee_id, meta)

    return out


def _build_questions_for_user(
    rows: list[dict[str, Any]],
    meta: dict[str, Any],
) -> list[dict[str, Any]]:
    """Transform DB rows into participant-facing question dicts."""
    jupyter_topics = set(meta["jupyter_topic_names"])
    topic_names_on_rows = list(
        dict.fromkeys((x.get("topic_name") or "").strip() for x in rows if x.get("topic_name"))
    )
    modality_by_name = db_service.get_topic_modality_by_names(topic_names_on_rows)
    editor_by_name = db_service.get_topic_coding_editor_by_names(topic_names_on_rows)

    questions_out: list[dict[str, Any]] = []
    for r in rows:
        qtype = (r.get("type") or "").lower()
        options = _parse_options(r.get("options") or "")
        tname = (r.get("topic_name") or "").strip()
        mod = resolve_question_modality(tname, jupyter_topics, modality_by_name)

        stored_code = (r.get("code_snippet") or "").strip()
        if stored_code:
            # The code_snippet was either set by the admin during review or was already
            # filtered by normalize_generated_question at save time.  Either way, trust it
            # directly so that admin edits (indentation corrections, prose moves) are not
            # silently discarded by the heuristic should_keep_stored_code check.
            prose = (r.get("question") or "").strip()
            code_snippet = prettify_inline_code(stored_code)
        else:
            prose, code_snippet = split_stem_for_display(r.get("question", ""), "")
            if code_snippet:
                code_snippet = prettify_inline_code(code_snippet)

        item: dict[str, Any] = {
            "question_id": r.get("question_id"),
            "type": qtype,
            "question": prose,
            "topic_name": tname,
            "topic_modality": mod if mod else None,
            "coding_editor_language": editor_by_name.get(tname) if tname else None,
            "options": options if qtype == "mcq" else [],
        }
        if code_snippet:
            item["code"] = code_snippet
        questions_out.append(item)
    return questions_out


def _parse_options(raw_opts: str) -> list[Any]:
    if not raw_opts:
        return []
    try:
        parsed = json.loads(raw_opts)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return list(parsed.values())
    except json.JSONDecodeError:
        pass
    return []


def _apply_timed_state(
    out: dict[str, Any],
    assessment_id: str,
    employee_id: str,
    meta: dict[str, Any],
) -> dict[str, Any]:
    """Add timer / already_submitted state for timed assessments."""
    if attempt_service.user_has_submitted(assessment_id, employee_id):
        out["already_submitted"] = True
        out["questions"] = []
        return out

    with get_session_factory()() as session:
        assessment_row = session.get(Assessment, assessment_id)
    if assessment_row and assessment_row.is_timed:
        out["timer"] = attempt_service.get_or_create_attempt(assessment_row, employee_id)
    return out


def submit_assessment(
    assessment_id: str,
    user_id: str,
    answers: list[dict[str, Any]],
    *,
    employee_id: str | None = None,
    submitter_client_id: str | None = None,
) -> dict[str, Any]:
    """Evaluate answers with the LLM, persist, and return scores + feedback."""
    stored = db_service.read_questions_by_assessment(assessment_id)
    if not stored:
        raise ValueError("Unknown assessment_id")

    meta = db_service.get_assessment_metadata(assessment_id)
    eid = (employee_id or attempt_service.parse_employee_id_from_user_label(user_id)).strip()

    if eid and attempt_service.user_has_submitted(assessment_id, eid):
        raise ValueError("You have already submitted this assessment.")

    if meta.get("is_timed") and eid:
        attempt_service.assert_main_submit_allowed(assessment_id, eid, is_timed=True)

    by_qid = {str(r["question_id"]): r for r in stored}
    ts = datetime.now(timezone.utc).isoformat()

    scores: list[float] = []
    feedback_parts: list[str] = []
    question_results: list[dict[str, Any]] = []

    for ans in answers:
        qid = str(ans.get("question_id", ""))
        user_text = str(ans.get("answer", "")).strip()
        row = by_qid.get(qid)
        if not row:
            continue

        question_text = format_question_for_grading(
            row.get("question", ""),
            row.get("code_snippet") or "",
        )
        qtype = (row.get("type") or "").lower()

        if qtype == "mcq" and row.get("options"):
            try:
                opts = json.loads(row["options"])
                if isinstance(opts, list):
                    question_text = (
                        f"{question_text}\nOptions: {', '.join(str(x) for x in opts)}"
                    )
            except json.JSONDecodeError:
                pass

        result = evaluate_answers(question_text, user_text)
        sc = float(result["score"])
        fb = result["feedback"]
        correct = _is_answer_correct(qtype, user_text, str(row.get("correct_answer") or ""), sc)
        scores.append(sc)
        feedback_parts.append(f"Q{qid}: {fb}")
        question_results.append({
                "question_id": qid,
                "score": round(sc, 2),
                "feedback": fb,
                "correct": correct,
        })

        db_service.save_submission_row(
            assessment_id, user_id, qid, user_text, str(sc), fb, ts,
            submitter_client_id=submitter_client_id,
        )

        question_bank_service.record_question_outcome(
            row.get("bank_question_id"), correct
        )
        if correct and eid:
            question_bank_service.record_employee_question_mastery(
                eid, row.get("bank_question_id")
            )

    if not scores:
        raise ValueError("No matching answers for this assessment")

    if meta.get("is_timed") and eid:
        attempt_service.mark_attempt_submitted(assessment_id, eid)

    return {
        "assessment_id": assessment_id,
        "user_id": user_id,
        "score": round(sum(scores) / len(scores), 2),
        "feedback": "\n".join(feedback_parts),
        "questions_graded": len(scores),
        "question_results": question_results,
    }
