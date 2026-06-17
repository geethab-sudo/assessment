"""Bank-only improvement assessments for client Help me improve flows (Stage 5+)."""

from __future__ import annotations

from typing import Any

from services import db_service
from services import employee_profile_service
from services import question_bank_service
from services.assessment_service import (
    _compute_routing_flag,
    _row_from_bank_item,
    _upsert_to_bank,
)
from services.ids import generate_assessment_id
from services.notebook_plan_service import (
    notebook_plan_from_rows,
    validate_notebook_plan_after_generation,
)

DEFAULT_QUESTIONS_REQUESTED = 15
MIN_QUESTIONS_REQUESTED = 1
MAX_QUESTIONS_REQUESTED = 50

_TYPE_ORDER = ("mcq", "coding", "subjective")

MSG_NO_HISTORY = (
    "Complete at least one assessment to unlock personalized practice recommendations."
)
MSG_NO_WEAK_TOPICS = (
    "No topics scored below 70% in your last 3 assessments. "
    "View your full report or try exploring new areas when available."
)
MSG_SHORTAGE_TEMPLATE = (
    "You asked for **{requested}** questions, but based on availability there are only "
    "**{delivered}** valid questions for you in our question bank."
)


def _resolve_language_label(language_code: str) -> str:
    from services.catalog_service import list_languages

    code = language_code.strip().lower()
    for lang in list_languages():
        if (lang.get("code") or "").strip().lower() == code:
            return (lang.get("name") or code).strip()
    return language_code.strip()


def _weak_areas_topic_summary(weakest_topics: list[str]) -> str:
    if not weakest_topics:
        return ""
    names = ", ".join(f"**{t}**" for t in weakest_topics)
    return (
        f"Based on your last 3 assessments, we recommend extra practice on: {names}."
    )


def _all_mastered_message(
    weakest_topics: list[str],
    difficulty_by_topic: dict[str, str],
) -> str:
    if len(weakest_topics) == 1:
        topic = weakest_topics[0]
        level = difficulty_by_topic.get(topic, "beginner")
        return (
            f"You have already answered all available questions correctly for **{topic}** "
            f"at **{level}** level. Great work — check back later or try another improvement path."
        )
    topics_str = ", ".join(f"**{t}**" for t in weakest_topics)
    return (
        f"You have already answered all available questions correctly for {topics_str}. "
        "Great work — check back later or try another improvement path."
    )


def _allocate_per_topic_config(
    weakest_topics: list[str],
    questions_requested: int,
) -> dict[str, dict[str, int]]:
    if not weakest_topics or questions_requested <= 0:
        return {}

    n = len(weakest_topics)
    base, remainder = divmod(questions_requested, n)
    config: dict[str, dict[str, int]] = {}

    for i, topic in enumerate(weakest_topics):
        total = base + (1 if i < remainder else 0)
        if total <= 0:
            config[topic] = {"mcq": 0, "coding": 0, "subjective": 0}
            continue
        if total == 1:
            config[topic] = {"mcq": 1, "coding": 0, "subjective": 0}
            continue
        mcq = max(1, round(total * 0.6))
        coding = total - mcq
        if coding < 0:
            mcq, coding = total, 0
        config[topic] = {"mcq": mcq, "coding": coding, "subjective": 0}

    return config


def _difficulty_by_topic(
    weakest_topics: list[str],
    topic_performance: list[dict[str, Any]],
) -> dict[str, str]:
    perf_by_name = {t["topic_name"]: t for t in topic_performance}
    result: dict[str, str] = {}
    for topic in weakest_topics:
        item = perf_by_name.get(topic) or {}
        level = (item.get("last_difficulty") or "beginner").strip().lower()
        if level not in ("beginner", "intermediate", "advanced"):
            level = "beginner"
        result[topic] = level
    return result


def _build_bank_only_rows(
    per_topic_config: dict[str, dict[str, int]],
    difficulty_by_topic: dict[str, str],
    employee_id: str,
) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    used_bank_ids: set[int] = set()
    global_q_id = 1
    total_shortage = 0

    for tname, cfg in per_topic_config.items():
        level = difficulty_by_topic.get(tname, "beginner")
        for qtype in _TYPE_ORDER:
            needed = int(cfg.get(qtype, 0) or 0)
            if needed <= 0:
                continue
            found, shortage = question_bank_service.find_bank_questions(
                [tname],
                level,
                needed,
                question_type=qtype,
                exclude_bank_ids=used_bank_ids,
                exclude_employee_id=employee_id,
            )
            for bq in found:
                rows.append(_row_from_bank_item(bq, global_q_id, level))
                used_bank_ids.add(int(bq["bank_question_id"]))
                global_q_id += 1
            total_shortage += shortage

    return rows, total_shortage


def _persist_bank_only_assessment(
    rows: list[dict[str, Any]],
    *,
    topic_names: list[str],
    per_topic_config: dict[str, dict[str, int]],
    language_code: str,
    language_label: str,
) -> str:
    assessment_id = generate_assessment_id()
    routing_flag = _compute_routing_flag(topic_names)
    plan = notebook_plan_from_rows(
        rows,
        topic_names=topic_names,
        per_topic_config=per_topic_config,
        routing_flag=routing_flag,
    )
    validate_notebook_plan_after_generation(plan)

    db_service.save_shared_assessment_rows(
        assessment_id,
        rows,
        routing_flag=routing_flag,
        language_code=language_code,
        language_label=language_label,
        topic_names=topic_names,
        is_timed=False,
        allow_pyodide_paste=False,
    )

    primary_level = (rows[0].get("difficulty") or "beginner") if rows else "beginner"
    _upsert_to_bank(assessment_id, rows, primary_level, language_code)

    return assessment_id


def create_weak_areas_assessment(
    employee_id: str,
    language_code: str,
    *,
    questions_requested: int | None = None,
) -> dict[str, Any]:
    """
    Build a bank-only practice assessment targeting weakest topics (last 3 assessments).

    Never calls the LLM. Mastered questions are excluded for the employee.
    """
    eid = (employee_id or "").strip()
    if not eid:
        raise ValueError("employee_id is required")

    lang = (language_code or "").strip()
    if not lang:
        raise ValueError("language_code is required")

    requested = (
        questions_requested
        if questions_requested is not None
        else DEFAULT_QUESTIONS_REQUESTED
    )
    requested = max(
        MIN_QUESTIONS_REQUESTED,
        min(MAX_QUESTIONS_REQUESTED, int(requested)),
    )

    profile = employee_profile_service.get_employee_profile(
        eid,
        language_code=lang,
        scope="last_3",
    )

    base_response: dict[str, Any] = {
        "employee_id": eid,
        "language_code": lang,
        "questions_requested": requested,
        "questions_delivered": 0,
        "assessment_id": None,
        "availability_message": None,
        "topic_summary": None,
        "weak_topics": [],
    }

    if profile["assessments_analyzed"] == 0:
        base_response["availability_message"] = MSG_NO_HISTORY
        return base_response

    weakest = list(profile.get("weakest_topics") or [])
    base_response["weak_topics"] = weakest

    if not weakest:
        base_response["availability_message"] = MSG_NO_WEAK_TOPICS
        return base_response

    base_response["topic_summary"] = _weak_areas_topic_summary(weakest)

    per_topic_config = _allocate_per_topic_config(weakest, requested)
    difficulty_map = _difficulty_by_topic(
        weakest,
        profile.get("topic_performance") or [],
    )

    rows, _shortage = _build_bank_only_rows(per_topic_config, difficulty_map, eid)
    delivered = len(rows)
    base_response["questions_delivered"] = delivered

    if delivered == 0:
        base_response["availability_message"] = _all_mastered_message(
            weakest, difficulty_map
        )
        return base_response

    if delivered < requested:
        base_response["availability_message"] = MSG_SHORTAGE_TEMPLATE.format(
            requested=requested,
            delivered=delivered,
        )

    language_label = _resolve_language_label(lang)
    assessment_id = _persist_bank_only_assessment(
        rows,
        topic_names=weakest,
        per_topic_config=per_topic_config,
        language_code=lang,
        language_label=language_label,
    )
    base_response["assessment_id"] = assessment_id
    return base_response
