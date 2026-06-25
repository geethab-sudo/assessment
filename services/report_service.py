"""
Build structured participant feedback reports (in-browser MCQ + Pyodide coding only).

Jupyter notebook submissions are intentionally excluded from v1 reports.
"""

from __future__ import annotations

from typing import Any

from services import db_service
from services.assessment_service import SCORE_CORRECT_THRESHOLD, _is_answer_correct
from services.attempt_service import parse_employee_id_from_user_label
from services.notebook_plan_service import resolve_question_modality
from services.question_stem import prettify_inline_code, split_stem_for_display

_NOTEBOOK_QUESTION_ID = "notebook"
_UNTOPPED_TOPIC_LABEL = "General"


def _submission_matches_employee(user_id: str, employee_id: str) -> bool:
    from services.attempt_service import submission_belongs_to_employee

    return submission_belongs_to_employee(user_id, employee_id)


def _parse_participant_name(user_id: str) -> str:
    parts = (user_id or "").split("|", 1)
    if len(parts) < 2:
        return ""
    return parts[1].strip()


def _is_jupyter_coding_row(
    row: dict[str, Any],
    jupyter_topics: set[str],
    modality_by_name: dict[str, str],
) -> bool:
    if (row.get("type") or "").lower() != "coding":
        return False
    tname = (row.get("topic_name") or "").strip()
    mod = resolve_question_modality(tname, jupyter_topics, modality_by_name)
    return mod == "jupyter"


def _question_display(row: dict[str, Any]) -> tuple[str, str | None]:
    stored_code = (row.get("code_snippet") or "").strip()
    if stored_code:
        prose = (row.get("question") or "").strip()
        code = prettify_inline_code(stored_code)
        return prose, code
    prose, code = split_stem_for_display(row.get("question", ""), "")
    if code:
        code = prettify_inline_code(code)
    return prose, code


def _question_correct_for_summary(q: dict[str, Any]) -> bool:
    if q.get("correct") is not None:
        return bool(q["correct"])
    return float(q.get("score") or 0) >= SCORE_CORRECT_THRESHOLD


def aggregate_topic_summary(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Roll up per-question scores into topic-level summary (correct count and average %)."""
    by_topic: dict[str, list[dict[str, Any]]] = {}
    for q in questions:
        topic = (q.get("topic_name") or "").strip() or _UNTOPPED_TOPIC_LABEL
        by_topic.setdefault(topic, []).append(q)

    summary: list[dict[str, Any]] = []
    for topic in sorted(by_topic.keys()):
        items = by_topic[topic]
        n = len(items)
        scores = [float(q["score"]) for q in items]
        correct_count = sum(1 for q in items if _question_correct_for_summary(q))
        avg = sum(scores) / n if n else 0.0
        summary.append(
            {
                "topic_name": topic,
                "questions_count": n,
                "correct_count": correct_count,
                "total_score": correct_count,
                "max_score": n,
                "average_score": round(avg, 2),
                "percent": round(avg, 2),
            }
        )
    return summary


def build_report(assessment_id: str, employee_id: str) -> dict[str, Any]:
    """
    Load in-browser submission rows for a participant and join with question metadata.

    Raises ValueError when the assessment is unknown or no in-browser submission exists.
    """
    eid = (employee_id or "").strip()
    if not eid:
        raise ValueError("employee_id is required")

    meta = db_service.get_assessment_metadata(assessment_id)
    if not db_service.read_questions_by_assessment(assessment_id):
        raise ValueError("Unknown assessment_id")

    raw_submissions = db_service.get_participant_in_browser_submissions(
        assessment_id, eid
    )
    if not raw_submissions:
        raise ValueError("No submission found for this participant")

    question_rows = db_service.read_questions_by_assessment(assessment_id)
    by_qid = {str(r["question_id"]): r for r in question_rows}
    jupyter_topics = set(meta.get("jupyter_topic_names") or [])
    topic_names = list(
        dict.fromkeys(
            (r.get("topic_name") or "").strip()
            for r in question_rows
            if (r.get("topic_name") or "").strip()
        )
    )
    modality_by_name = db_service.get_topic_modality_by_names(topic_names)

    sub_by_qid = {str(s["question_id"]): s for s in raw_submissions}
    user_id = raw_submissions[0]["user_id"]
    submitted_at = max(s["timestamp"] for s in raw_submissions if s.get("timestamp"))

    report_questions: list[dict[str, Any]] = []
    position = 0
    for row in question_rows:
        qid = str(row["question_id"])
        sub = sub_by_qid.get(qid)
        if not sub:
            continue
        if _is_jupyter_coding_row(row, jupyter_topics, modality_by_name):
            continue

        position += 1
        qtype = (row.get("type") or "").lower()
        prose, code = _question_display(row)
        score = float(sub.get("score") or 0)
        user_answer = str(sub.get("user_answer") or "")
        correct = _is_answer_correct(
            qtype,
            user_answer,
            str(row.get("correct_answer") or ""),
            score,
        )

        item: dict[str, Any] = {
            "question_id": qid,
            "position": position,
            "type": qtype,
            "topic_name": (row.get("topic_name") or "").strip() or _UNTOPPED_TOPIC_LABEL,
            "question": prose,
            "user_answer": user_answer,
            "score": round(score, 2),
            "correct": correct,
            "feedback": str(sub.get("feedback") or ""),
        }
        if code:
            item["code"] = code
        report_questions.append(item)

    if not report_questions:
        raise ValueError("No in-browser submission found for this participant")

    scores = [float(q["score"]) for q in report_questions]
    overall = round(sum(scores) / len(scores), 2) if scores else 0.0

    return {
        "assessment_id": assessment_id,
        "participant": {
            "employee_id": parse_employee_id_from_user_label(user_id) or eid,
            "name": _parse_participant_name(user_id),
            "user_id": user_id,
        },
        "submitted_at": submitted_at,
        "overall_score": overall,
        "questions_graded": len(report_questions),
        "score_correct_threshold": SCORE_CORRECT_THRESHOLD,
        "questions": report_questions,
        "topic_summary": aggregate_topic_summary(report_questions),
        "report_scope": "in_browser",
    }
