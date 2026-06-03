"""
Orchestrates LLM calls and database reads/writes for assessments and submissions.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from services import db_service
from services.llm_service import evaluate_answers, generate_questions
from services.shuffle_service import apply_participant_shuffle
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
) -> dict[str, Any]:
    """Generate questions via LLM and persist rows (shared assessment in PostgreSQL).

    When `per_topic_config` maps topic names to per-type counts, each topic is sent to
    the LLM separately so questions can be tagged with their originating topic name.
    """
    difficulty = LEVEL_TO_DIFFICULTY.get(level.strip().lower())
    if not difficulty:
        raise ValueError("level must be one of: beginner, intermediate, advanced")
    assessment_id = str(uuid.uuid4())

    rows: list[dict[str, Any]] = []

    if per_topic_config and topic_names:
        # Per-topic generation: one LLM call per topic so questions carry a topic_name tag.
        from services.llm_service import generate_questions as _gen  # local to avoid circular
        from services import catalog_service as _cat

        # Build a name→topic row map for fetching topic text (related docs etc.)
        # We need to reconstruct the topic string for each topic the same way AdminPage does.
        topic_strings: dict[str, str] = _build_per_topic_strings(topic_names)

        global_q_id = 1
        for tname in topic_names:
            cfg = per_topic_config.get(tname) or {}
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
        # Legacy single-call generation (no per-topic config).
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

    db_service.save_shared_assessment_rows(
        assessment_id,
        rows,
        language_code=language_code,
        language_label=language_label,
        topic_names=topic_names if topic_names is not None else [],
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
        "topic_names": list(topic_names or []),
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
    if not rows:
        return {
            "assessment_id": assessment_id,
            "questions": [],
            "found": False,
            "language_code": meta["language_code"],
            "routing_flag": meta["routing_flag"],
            "topic_names": meta["topic_names"],
            "jupyter_topic_names": meta["jupyter_topic_names"],
        }

    jupyter_topics = set(meta["jupyter_topic_names"])

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

        tname = r.get("topic_name") or ""
        # Determine per-question modality: if the question is tagged to a jupyter topic → jupyter
        if tname and tname in jupyter_topics:
            topic_modality = "jupyter"
        elif tname:
            topic_modality = "pyodide"
        else:
            topic_modality = None  # legacy question with no topic tag

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

    return {
        "assessment_id": assessment_id,
        "language_code": meta["language_code"],
        "questions": questions_out,
        "found": True,
        "routing_flag": meta["routing_flag"],
        "topic_names": meta["topic_names"],
        "jupyter_topic_names": meta["jupyter_topic_names"],
    }


def submit_assessment(
    assessment_id: str,
    user_id: str,
    answers: list[dict[str, Any]],
    *,
    submitter_client_id: str | None = None,
) -> dict[str, Any]:
    """
    Load stored questions, evaluate each answer with the LLM, persist submission rows,
    and return aggregate score and combined feedback.
    """
    stored = db_service.read_questions_by_assessment(assessment_id)
    if not stored:
        raise ValueError("Unknown assessment_id")

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

    return {
        "assessment_id": assessment_id,
        "user_id": user_id,
        "score": overall,
        "feedback": combined_feedback,
        "questions_graded": len(scores),
        "question_results": question_results,
    }
