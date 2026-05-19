"""
Orchestrates LLM calls and database reads/writes for assessments and submissions.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from services import db_service
from services.llm_service import evaluate_answers, generate_questions
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
) -> dict[str, Any]:
    """Generate questions via LLM and persist rows (shared assessment in PostgreSQL)."""
    difficulty = LEVEL_TO_DIFFICULTY.get(level.strip().lower())
    if not difficulty:
        raise ValueError("level must be one of: beginner, intermediate, advanced")
    if set(types) != set(questions_per_type.keys()):
        raise ValueError("types and questions_per_type keys must match")
    assessment_id = str(uuid.uuid4())
    questions = generate_questions(
        topic,
        difficulty,
        types,
        questions_per_type=questions_per_type,
        assessment_id=assessment_id,
    )

    rows: list[dict[str, Any]] = []
    for q in questions:
        opts = q.get("options") or []
        rows.append(
            {
                "question_id": q.get("id"),
                "question": q["question"],
                "type": q["type"],
                "options": _options_for_csv(opts),
                "correct_answer": q.get("answer", ""),
            }
        )

    db_service.save_shared_assessment_rows(
        assessment_id,
        rows,
        language_code=language_code,
        language_label=language_label,
        topic_names=topic_names if topic_names is not None else [],
        creation_mode="generated",
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


def create_manual_assessment(
    questions: list[dict[str, Any]],
    *,
    language_code: str | None = None,
    language_label: str | None = None,
    topic_names: list[str] | None = None,
) -> dict[str, Any]:
    """Persist admin-authored MCQ / coding / subjective questions (no LLM)."""
    if not questions:
        raise ValueError("Add at least one question")
    has_coding = any(
        (q.get("type") or "").strip().lower() == "coding" for q in questions
    )
    if has_coding and not (language_code or "").strip():
        raise ValueError(
            "Select a catalog language when the assessment includes coding questions"
        )
    assessment_id = str(uuid.uuid4())
    rows: list[dict[str, Any]] = []
    for i, q in enumerate(questions, start=1):
        qtype = (q.get("type") or "").strip().lower()
        if qtype not in ("mcq", "coding", "subjective"):
            raise ValueError(f"Question {i}: type must be mcq, coding, or subjective")
        stem = (q.get("question") or "").strip()
        if not stem:
            raise ValueError(f"Question {i}: question text is required")
        opts_raw = q.get("options") or []
        if not isinstance(opts_raw, list):
            raise ValueError(f"Question {i}: options must be a list")
        options = [str(o).strip() for o in opts_raw if str(o).strip()]
        correct = (q.get("correct_answer") or "").strip()
        if qtype == "mcq":
            if len(options) < 2:
                raise ValueError(f"Question {i}: MCQ needs at least two options")
            if not correct:
                raise ValueError(f"Question {i}: select the correct MCQ answer")
            if correct.casefold() not in {o.casefold() for o in options}:
                raise ValueError(
                    f"Question {i}: correct answer must match one of the options exactly"
                )
        elif qtype == "coding":
            options = []
        else:
            options = []
        rows.append(
            {
                "question_id": str(i),
                "question": stem,
                "type": qtype,
                "options": _options_for_csv(options),
                "correct_answer": correct,
            }
        )
    db_service.save_shared_assessment_rows(
        assessment_id,
        rows,
        language_code=language_code,
        language_label=language_label,
        topic_names=topic_names if topic_names is not None else [],
        creation_mode="manual",
    )
    return {
        "assessment_id": assessment_id,
        "creation_mode": "manual",
        "question_count": len(rows),
        "language_code": (language_code or "").strip()[:32] or None,
        "language_label": (language_label or "").strip()[:256] or None,
        "topic_names": list(topic_names or []),
    }


def get_assessment_for_user(assessment_id: str) -> dict[str, Any]:
    """
    Return assessment metadata and questions without revealing correct answers.
    """
    rows = db_service.read_questions_by_assessment(assessment_id)
    if not rows:
        return {
            "assessment_id": assessment_id,
            "questions": [],
            "found": False,
            "language_code": db_service.get_assessment_language_code(assessment_id),
        }

    language_code = db_service.get_assessment_language_code(assessment_id)
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

        item: dict[str, Any] = {
            "question_id": r.get("question_id"),
            "type": qtype,
            "question": r.get("question", ""),
        }
        if qtype == "mcq":
            item["options"] = options
        else:
            item["options"] = []
        questions_out.append(item)

    return {
        "assessment_id": assessment_id,
        "language_code": language_code,
        "questions": questions_out,
        "found": True,
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
