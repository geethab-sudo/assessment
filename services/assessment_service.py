"""
Orchestrates LLM calls and database reads/writes for assessments and submissions.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from services import db_service
from services.llm_service import evaluate_answers, generate_questions
from services import attempt_service
from services.shuffle_service import apply_participant_shuffle
from services.notebook_plan_service import (
    derive_per_topic_config,
    notebook_plan_for_assessment,
    notebook_plan_from_rows,
    resolve_question_modality,
    validate_notebook_plan_after_generation,
)
from services.database import get_session_factory
from services.models import Assessment
import uuid


def _options_for_csv(options: Any) -> str:
    """Serialize options list/dict to a JSON string for CSV storage."""
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
    *,
    score_threshold: float = 70.0,
) -> bool:
    """MCQ: match stored correct answer; other types: score meets threshold."""
    if qtype == "mcq":
        return (
            user_text.strip().casefold() == (correct_answer or "").strip().casefold()
        )
    return score >= score_threshold


LEVEL_TO_DIFFICULTY = {
    "beginner": "easy",
    "intermediate": "medium",
    "advanced": "hard",
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
    """Generate questions via LLM and persist rows (shared assessment in PostgreSQL).

    When `per_topic_config` maps topic names to per-type counts, each topic is sent to
    the LLM separately so questions can be tagged with their originating topic name.
    """
    difficulty = LEVEL_TO_DIFFICULTY.get(level.strip().lower())
    if not difficulty:
        raise ValueError("level must be one of: beginner, intermediate, advanced")
    assessment_id = str(uuid.uuid4())
    dur, grace = attempt_service.validate_timed_config(
        is_timed, duration_minutes, notebook_grace_minutes
    )

    rows: list[dict[str, Any]] = []
    catalog_topic_names = [
        n.strip() for n in (topic_names or []) if n and str(n).strip()
    ]
    effective_per_topic: dict[str, dict[str, int]] | None = None
    if catalog_topic_names:
        effective_per_topic = (
            per_topic_config
            if per_topic_config
            else derive_per_topic_config(
                catalog_topic_names, types, questions_per_type
            )
        )

    if effective_per_topic and catalog_topic_names:
        # Per-topic generation: one LLM call per topic so questions carry a topic_name tag.
        from services.llm_service import generate_questions as _gen  # local to avoid circular

        topic_strings: dict[str, str] = _build_per_topic_strings(catalog_topic_names)

        global_q_id = 1
        for tname in catalog_topic_names:
            cfg = effective_per_topic.get(tname) or {}
            t_types = [t for t in types if cfg.get(t, 0) > 0]
            t_counts = {t: cfg[t] for t in t_types}
            if not t_types:
                continue
            t_topic_str = topic_strings.get(tname, tname)
            t_questions = _gen(
                t_topic_str,
                difficulty,
                t_types,
                questions_per_type=t_counts,
                assessment_id=f"{assessment_id}-{tname[:32]}",
            )
            for q in t_questions:
                opts = q.get("options") or []
                rows.append({
                    "question_id": str(global_q_id),
                    "question": q["question"],
                    "type": q["type"],
                    "options": _options_for_csv(opts),
                    "correct_answer": q.get("answer", ""),
                    "topic_name": tname,
                })
                global_q_id += 1
    else:
        # Legacy single-call generation (custom topic or no catalog topics).
        if set(types) != set(questions_per_type.keys()):
            raise ValueError("types and questions_per_type keys must match")
        questions = generate_questions(
            topic,
            difficulty,
            types,
            questions_per_type=questions_per_type,
            assessment_id=assessment_id,
        )
        for q in questions:
            opts = q.get("options") or []
            rows.append({
                "question_id": q.get("id"),
                "question": q["question"],
                "type": q["type"],
                "options": _options_for_csv(opts),
                "correct_answer": q.get("answer", ""),
                "topic_name": "",
            })

    from services.notebook_plan_service import jupyter_topic_names_from_list

    routing_flag = "pyodide"
    if catalog_topic_names:
        jupyter_topics = jupyter_topic_names_from_list(catalog_topic_names)
        has_jupyter = bool(jupyter_topics)
        has_other = any(t not in set(jupyter_topics) for t in catalog_topic_names)
        if has_jupyter and has_other:
            routing_flag = "mixed"
        elif has_jupyter:
            routing_flag = "jupyter"

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
        language_code=language_code,
        language_label=language_label,
        topic_names=topic_names if topic_names is not None else [],
        is_timed=is_timed,
        duration_minutes=dur,
        notebook_grace_minutes=grace,
    )
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


def _build_per_topic_strings(topic_names: list[str]) -> dict[str, str]:
    """Build LLM topic strings for each catalog topic name by looking up related_documents."""
    from sqlalchemy import select
    from services.database import get_session_factory
    from services.models import Topic

    result: dict[str, str] = {}
    try:
        sf = get_session_factory()
        with sf() as session:
            rows = session.scalars(
                select(Topic).where(Topic.name.in_(topic_names))
            ).all()
            by_name = {r.name: r for r in rows}
    except Exception:
        by_name = {}

    for tname in topic_names:
        row = by_name.get(tname)
        if not row:
            result[tname] = tname
            continue
        docs = row.related_documents or []
        if not docs:
            result[tname] = tname
            continue
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
        result[tname] = f"{tname}\n\nContext (reference materials):\n" + "\n".join(lines)
    return result


def get_notebook_template_questions(assessment_id: str) -> list[dict[str, Any]]:
    """
    Coding questions that belong in the downloadable .ipynb (jupyter-modality only).

    Uses DB question rows in canonical order. Never includes pyodide-tier coding
    questions for mixed assessments.
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
            notebook_questions.append(
                {
                    "question_id": r.get("question_id"),
                    "question": r.get("question", ""),
                    "topic_name": tname,
                }
            )

    if not notebook_questions and routing_flag == "jupyter":
        for r in rows:
            if (r.get("type") or "").lower() == "coding":
                notebook_questions.append(
                    {
                        "question_id": r.get("question_id"),
                        "question": r.get("question", ""),
                        "topic_name": r.get("topic_name") or "",
                    }
                )

    return notebook_questions


def get_assessment_for_user(
    assessment_id: str,
    *,
    employee_id: str | None = None,
) -> dict[str, Any]:
    """
    Return assessment metadata and questions without revealing correct answers.

    The ``*`` in the signature makes ``employee_id`` keyword-only: callers must pass
    ``employee_id="E1001"``, not as a second positional argument. That keeps
    ``assessment_id`` unambiguous and avoids mistakes if more optional params are added.

    When ``employee_id`` is provided, question order and MCQ option order are
    shuffled deterministically for that participant (assessment_id + employee_id).
    Admin preview and notebook templates should omit ``employee_id`` for canonical order.
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

    if not rows:
        return {
            "assessment_id": assessment_id,
            "questions": [],
            "found": False,
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

    jupyter_topics = set(meta["jupyter_topic_names"])
    modality_by_name = db_service.get_topic_modality_by_names(
        list(dict.fromkeys((x.get("topic_name") or "").strip() for x in rows if x.get("topic_name")))
    )

    questions_out: list[dict[str, Any]] = []
    for r in rows:
        qtype = (r.get("type") or "").lower()
        raw_opts = r.get("options") or ""
        options: list[Any] = []
        if raw_opts:
            try:
                parsed = json.loads(raw_opts)
                if isinstance(parsed, list):
                    options = parsed
                elif isinstance(parsed, dict):
                    options = list(parsed.values())
            except json.JSONDecodeError:
                options = []

        tname = (r.get("topic_name") or "").strip()
        mod = resolve_question_modality(tname, jupyter_topics, modality_by_name)
        topic_modality = mod if mod else None

        item: dict[str, Any] = {
            "question_id": r.get("question_id"),
            "type": qtype,
            "question": r.get("question", ""),
            "topic_name": tname,
            "topic_modality": topic_modality,
        }
        if qtype == "mcq":
            item["options"] = options
        else:
            item["options"] = []
        questions_out.append(item)

    if employee_id and employee_id.strip():
        questions_out = apply_participant_shuffle(
            assessment_id, employee_id.strip(), questions_out
        )

    out: dict[str, Any] = {
        "assessment_id": assessment_id,
        "language_code": meta["language_code"],
        "questions": questions_out,
        "found": True,
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

    if meta.get("is_timed") and employee_id and employee_id.strip():
        if attempt_service.user_has_submitted(assessment_id, employee_id):
            out["already_submitted"] = True
            out["questions"] = []
        else:
            sf = get_session_factory()
            with sf() as session:
                assessment_row = session.get(Assessment, assessment_id)
            if assessment_row and assessment_row.is_timed:
                out["timer"] = attempt_service.get_or_create_attempt(
                    assessment_row, employee_id
                )

    return out


def submit_assessment(
    assessment_id: str,
    user_id: str,
    answers: list[dict[str, Any]],
    *,
    employee_id: str | None = None,
    submitter_client_id: str | None = None,
) -> dict[str, Any]:
    """
    Load stored questions, evaluate each answer with the LLM, persist submission rows,
    and return aggregate score and combined feedback.
    """
    stored = db_service.read_questions_by_assessment(assessment_id)
    if not stored:
        raise ValueError("Unknown assessment_id")

    meta = db_service.get_assessment_metadata(assessment_id)
    eid = (employee_id or attempt_service.parse_employee_id_from_user_label(user_id)).strip()
    if meta.get("is_timed") and eid:
        attempt_service.assert_main_submit_allowed(
            assessment_id, eid, is_timed=True
        )

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

        question_text = row.get("question", "")
        qtype = (row.get("type") or "").lower()

        # Include options in prompt for MCQ so the model sees full context
        if qtype == "mcq" and row.get("options"):
            try:
                opts = json.loads(row["options"])
                if isinstance(opts, list):
                    question_text = f"{question_text}\nOptions: {', '.join(str(x) for x in opts)}"
            except json.JSONDecodeError:
                pass

        result = evaluate_answers(question_text, user_text)
        sc = float(result["score"])
        fb = result["feedback"]
        correct = _is_answer_correct(
            qtype,
            user_text,
            str(row.get("correct_answer") or ""),
            sc,
        )
        scores.append(sc)
        feedback_parts.append(f"Q{qid}: {fb}")
        question_results.append(
            {
                "question_id": qid,
                "score": round(sc, 2),
                "feedback": fb,
                "correct": correct,
            }
        )

        db_service.save_submission_row(
            assessment_id,
            user_id,
            qid,
            user_text,
            str(sc),
            fb,
            ts,
            submitter_client_id=submitter_client_id,
        )

    if not scores:
        raise ValueError("No matching answers for this assessment")

    overall = round(sum(scores) / len(scores), 2)
    combined_feedback = "\n".join(feedback_parts)

    if meta.get("is_timed") and eid:
        attempt_service.mark_attempt_submitted(assessment_id, eid)

    return {
        "assessment_id": assessment_id,
        "user_id": user_id,
        "score": overall,
        "feedback": combined_feedback,
        "questions_graded": len(scores),
        "question_results": question_results,
    }
