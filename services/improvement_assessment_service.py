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

from services.improvement_constants import (
    DEFAULT_QUESTIONS_REQUESTED,
    DEFAULT_QUICK_PRACTICE_QUESTIONS,
    MAX_QUESTIONS_PER_TOPIC,
    MAX_QUESTIONS_REQUESTED,
    MAX_TOPICS_PER_SESSION,
    MIN_QUESTIONS_REQUESTED,
    PROFICIENCY_THRESHOLD_PERCENT,
)

DEFAULT_NEW_AREAS_TOPIC_COUNT = MAX_TOPICS_PER_SESSION
DEFAULT_STEP_UP_TOPIC_COUNT = MAX_TOPICS_PER_SESSION

_DIFFICULTY_RANK = {"beginner": 1, "intermediate": 2, "advanced": 3}

_TYPE_ORDER = ("mcq", "coding", "subjective")

MSG_NO_HISTORY = (
    "Complete at least one assessment to unlock personalized practice recommendations."
)
MSG_NO_FOCUS_TOPICS = (
    f"No topics scored below {PROFICIENCY_THRESHOLD_PERCENT:.0f}% in your last 3 assessments. "
    "View your full report or try exploring new areas when available."
)
MSG_NO_UNEXPLORED = (
    "You have already explored all catalog topics for this language. "
    "Try focus areas or step up difficulty when available."
)
MSG_NO_STEP_UP = (
    "No topics are ready for a harder level yet. Score at least **75%** on beginner "
    "topics (or **80%** on intermediate) to unlock step-up practice."
)
MSG_NO_BANK_FOR_TOPICS = (
    "We could not find practice questions in the bank for the selected topics at the "
    "appropriate difficulty. Try again later or choose another improvement path."
)
MSG_SHORTAGE_TEMPLATE = (
    "You asked for **{requested}** questions, but based on availability there are only "
    "**{delivered}** valid questions for you in our question bank."
)


def _difficulty_for_new_area_topic(topic: str, assessed_level: str) -> str:
    """Tier 2+ use topic-inferred bank level; Tier 1 follows the employee's assessed tier."""
    from services.employee_profile_service import _topic_tier_number

    if _topic_tier_number(topic) >= 2:
        return question_bank_service.infer_bank_level_from_topic(topic)
    level = (assessed_level or "beginner").strip().lower()
    if level not in ("beginner", "intermediate", "advanced"):
        level = "beginner"
    return level


def _topics_have_bank_questions(
    topics: list[str],
    difficulty_by_topic: dict[str, str],
) -> bool:
    """True if the bank has at least one question for any topic (ignoring mastery)."""
    for topic in topics:
        level = difficulty_by_topic.get(topic, "beginner")
        found, _ = question_bank_service.find_bank_questions(
            [topic],
            level,
            1,
            exclude_employee_id=None,
        )
        if found:
            return True
    return False


def _clamp_questions_requested(questions_requested: int | None) -> int:
    requested = (
        questions_requested
        if questions_requested is not None
        else DEFAULT_QUESTIONS_REQUESTED
    )
    return max(
        MIN_QUESTIONS_REQUESTED,
        min(MAX_QUESTIONS_REQUESTED, int(requested)),
    )


def _clamp_topic_names(topic_names: list[str] | None, *, max_topics: int) -> list[str]:
    if not topic_names:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for raw in topic_names:
        name = (raw or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
        if len(out) >= max_topics:
            break
    return out


def _improvement_base_response(
    eid: str,
    lang: str,
    requested: int,
) -> dict[str, Any]:
    return {
        "employee_id": eid,
        "language_code": lang,
        "questions_requested": requested,
        "questions_delivered": 0,
        "assessment_id": None,
        "availability_message": None,
        "topic_summary": None,
    }


def _resolve_language_label(language_code: str) -> str:
    from services.catalog_service import list_languages

    code = language_code.strip().lower()
    for lang in list_languages():
        if (lang.get("code") or "").strip().lower() == code:
            return (lang.get("name") or code).strip()
    return language_code.strip()


def _weak_areas_topic_summary(focus_topics: list[str]) -> str:
    if not focus_topics:
        return ""
    names = ", ".join(f"**{t}**" for t in focus_topics)
    return (
        f"Based on your last 3 assessments, we recommend extra practice on: {names}."
    )


def _new_areas_topic_summary(selected_topics: list[str]) -> str:
    if not selected_topics:
        return ""
    names = ", ".join(f"**{t}**" for t in selected_topics)
    return (
        "Based on your full assessment history, we selected topics you have not tried yet: "
        f"{names}."
    )


def _difficulty_step_up_topic_summary(
    selected_topics: list[str],
    target_difficulty_by_topic: dict[str, str],
) -> str:
    if not selected_topics:
        return ""
    parts = []
    for topic in selected_topics:
        level = target_difficulty_by_topic.get(topic, "intermediate")
        parts.append(f"**{topic}** ({level})")
    return (
        "Based on your full assessment history, practice at the next difficulty level on: "
        + ", ".join(parts)
        + "."
    )


def _normalize_difficulty(level: str | None) -> str:
    d = (level or "beginner").strip().lower()
    if d not in _DIFFICULTY_RANK:
        return "beginner"
    return d


def _select_step_up_topics(
    topic_performance: list[dict[str, Any]],
    recommended_by_topic: dict[str, str],
    *,
    limit: int,
) -> tuple[list[str], dict[str, str]]:
    """
    Topics where recommended difficulty is strictly higher than last assessed level.

    Strongest performers (highest average %) are preferred when limiting topic count.
    """
    candidates: list[tuple[float, str, str]] = []
    for item in topic_performance:
        topic = item.get("topic_name") or ""
        if not topic:
            continue
        last = _normalize_difficulty(item.get("last_difficulty"))
        target = _normalize_difficulty(recommended_by_topic.get(topic, last))
        if _DIFFICULTY_RANK[target] > _DIFFICULTY_RANK[last]:
            candidates.append((float(item.get("average_percent") or 0), topic, target))

    candidates.sort(key=lambda row: (-row[0], row[1].casefold()))
    selected: list[str] = []
    targets: dict[str, str] = {}
    for _avg, topic, target in candidates[:limit]:
        selected.append(topic)
        targets[topic] = target
    return selected, targets


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
    topics: list[str],
    questions_requested: int,
) -> dict[str, dict[str, int]]:
    if not topics or questions_requested <= 0:
        return {}

    n = len(topics)
    capped_total = min(questions_requested, n * MAX_QUESTIONS_PER_TOPIC)
    base, remainder = divmod(capped_total, n)
    config: dict[str, dict[str, int]] = {}

    for i, topic in enumerate(topics):
        total = min(MAX_QUESTIONS_PER_TOPIC, base + (1 if i < remainder else 0))
        if total <= 0:
            config[topic] = {"mcq": 0, "coding": 0, "subjective": 0}
            continue
        if total == 1:
            config[topic] = {"mcq": 1, "coding": 0, "subjective": 0}
            continue
        mcq = max(1, round(total * 0.6))
        coding = min(MAX_QUESTIONS_PER_TOPIC, total) - mcq
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
    topic_names: list[str] | None = None,
) -> dict[str, Any]:
    """
    Build a bank-only practice assessment on focus topics (last 3 assessments).

    Never calls the LLM. Mastered questions are excluded for the employee.
    """
    eid = (employee_id or "").strip()
    if not eid:
        raise ValueError("employee_id is required")

    lang = (language_code or "").strip()
    if not lang:
        raise ValueError("language_code is required")

    requested = _clamp_questions_requested(questions_requested)

    profile = employee_profile_service.get_employee_profile(
        eid,
        language_code=lang,
        scope="last_3",
    )

    base_response = _improvement_base_response(eid, lang, requested)
    base_response["weak_topics"] = []
    base_response["focus_topics"] = []

    if profile["assessments_analyzed"] == 0:
        base_response["availability_message"] = MSG_NO_HISTORY
        return base_response

    eligible = list(profile.get("weakest_topics") or [])
    if topic_names:
        picked = _clamp_topic_names(topic_names, max_topics=MAX_TOPICS_PER_SESSION)
        selected = [t for t in picked if t in eligible]
        if not selected:
            raise ValueError(
                "Selected topics are not focus areas for your recent assessments."
            )
    else:
        selected = eligible

    base_response["weak_topics"] = selected
    base_response["focus_topics"] = selected

    if not selected:
        base_response["availability_message"] = MSG_NO_FOCUS_TOPICS
        return base_response

    base_response["topic_summary"] = _weak_areas_topic_summary(selected)

    per_topic_config = _allocate_per_topic_config(selected, requested)
    difficulty_map = _difficulty_by_topic(
        selected,
        profile.get("topic_performance") or [],
    )

    rows, _shortage = _build_bank_only_rows(per_topic_config, difficulty_map, eid)
    delivered = len(rows)
    base_response["questions_delivered"] = delivered

    if delivered == 0:
        base_response["availability_message"] = _all_mastered_message(
            selected, difficulty_map
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
        topic_names=selected,
        per_topic_config=per_topic_config,
        language_code=lang,
        language_label=language_label,
    )
    base_response["assessment_id"] = assessment_id
    return base_response


def create_new_areas_assessment(
    employee_id: str,
    language_code: str,
    *,
    questions_requested: int | None = None,
    topics_count: int | None = None,
    topic_names: list[str] | None = None,
) -> dict[str, Any]:
    """
    Build a bank-only practice assessment on unexplored catalog topics (full history).

    Never calls the LLM. Mastered questions are excluded for the employee.
    """
    from services.employee_profile_service import _pick_unexplored_for_recommendations

    eid = (employee_id or "").strip()
    if not eid:
        raise ValueError("employee_id is required")

    lang = (language_code or "").strip()
    if not lang:
        raise ValueError("language_code is required")

    requested = _clamp_questions_requested(questions_requested)
    k = topics_count if topics_count is not None else DEFAULT_NEW_AREAS_TOPIC_COUNT
    k = max(1, min(MAX_TOPICS_PER_SESSION, int(k)))

    profile = employee_profile_service.get_employee_profile(
        eid,
        language_code=lang,
        scope="full_history",
    )

    base_response = _improvement_base_response(eid, lang, requested)
    base_response["selected_topics"] = []

    if profile["assessments_analyzed"] == 0:
        base_response["availability_message"] = MSG_NO_HISTORY
        return base_response

    unexplored = list(profile.get("unexplored_topic_names") or [])
    if not unexplored:
        base_response["availability_message"] = MSG_NO_UNEXPLORED
        return base_response

    if topic_names:
        picked = _clamp_topic_names(topic_names, max_topics=MAX_TOPICS_PER_SESSION)
        selected = [t for t in picked if t in unexplored]
        if not selected:
            raise ValueError("Selected topics are not unexplored for this language.")
    else:
        from services.employee_profile_service import _pick_unexplored_for_recommendations

        selected = _pick_unexplored_for_recommendations(unexplored, limit=k)
    base_response["selected_topics"] = selected
    base_response["topic_summary"] = _new_areas_topic_summary(selected)

    assessed_level = str(profile.get("assessed_level") or "beginner")
    per_topic_config = _allocate_per_topic_config(selected, requested)
    difficulty_map = {
        topic: _difficulty_for_new_area_topic(topic, assessed_level)
        for topic in selected
    }

    rows, _shortage = _build_bank_only_rows(per_topic_config, difficulty_map, eid)
    delivered = len(rows)
    base_response["questions_delivered"] = delivered

    if delivered == 0:
        if _topics_have_bank_questions(selected, difficulty_map):
            base_response["availability_message"] = _all_mastered_message(
                selected, difficulty_map
            )
        else:
            base_response["availability_message"] = MSG_NO_BANK_FOR_TOPICS
        return base_response

    if delivered < requested:
        base_response["availability_message"] = MSG_SHORTAGE_TEMPLATE.format(
            requested=requested,
            delivered=delivered,
        )

    language_label = _resolve_language_label(lang)
    assessment_id = _persist_bank_only_assessment(
        rows,
        topic_names=selected,
        per_topic_config=per_topic_config,
        language_code=lang,
        language_label=language_label,
    )
    base_response["assessment_id"] = assessment_id
    return base_response


def create_difficulty_improvement_assessment(
    employee_id: str,
    language_code: str,
    *,
    questions_requested: int | None = None,
    topics_count: int | None = None,
    topic_names: list[str] | None = None,
) -> dict[str, Any]:
    """
    Build a bank-only practice assessment at stepped-up difficulty on familiar topics.

    Uses full-history ``recommended_difficulty_by_topic``; never calls the LLM.
    """
    eid = (employee_id or "").strip()
    if not eid:
        raise ValueError("employee_id is required")

    lang = (language_code or "").strip()
    if not lang:
        raise ValueError("language_code is required")

    requested = _clamp_questions_requested(questions_requested)
    k = topics_count if topics_count is not None else DEFAULT_STEP_UP_TOPIC_COUNT
    k = max(1, min(MAX_TOPICS_PER_SESSION, int(k)))

    profile = employee_profile_service.get_employee_profile(
        eid,
        language_code=lang,
        scope="full_history",
    )

    base_response = _improvement_base_response(eid, lang, requested)
    base_response["selected_topics"] = []
    base_response["target_difficulty_by_topic"] = {}

    if profile["assessments_analyzed"] == 0:
        base_response["availability_message"] = MSG_NO_HISTORY
        return base_response

    recommended = dict(profile.get("recommended_difficulty_by_topic") or {})
    all_selected, difficulty_map = _select_step_up_topics(
        profile.get("topic_performance") or [],
        recommended,
        limit=k,
    )
    if topic_names:
        picked = _clamp_topic_names(topic_names, max_topics=MAX_TOPICS_PER_SESSION)
        eligible = set(all_selected)
        selected = [t for t in picked if t in eligible]
        if not selected:
            raise ValueError("Selected topics are not ready for step-up practice.")
        difficulty_map = {t: difficulty_map[t] for t in selected}
    else:
        selected = all_selected
    base_response["selected_topics"] = selected
    base_response["target_difficulty_by_topic"] = difficulty_map

    if not selected:
        base_response["availability_message"] = MSG_NO_STEP_UP
        return base_response

    base_response["topic_summary"] = _difficulty_step_up_topic_summary(
        selected, difficulty_map
    )

    per_topic_config = _allocate_per_topic_config(selected, requested)
    rows, _shortage = _build_bank_only_rows(per_topic_config, difficulty_map, eid)
    delivered = len(rows)
    base_response["questions_delivered"] = delivered

    if delivered == 0:
        if _topics_have_bank_questions(selected, difficulty_map):
            base_response["availability_message"] = _all_mastered_message(
                selected, difficulty_map
            )
        else:
            base_response["availability_message"] = MSG_NO_BANK_FOR_TOPICS
        return base_response

    if delivered < requested:
        base_response["availability_message"] = MSG_SHORTAGE_TEMPLATE.format(
            requested=requested,
            delivered=delivered,
        )

    language_label = _resolve_language_label(lang)
    assessment_id = _persist_bank_only_assessment(
        rows,
        topic_names=selected,
        per_topic_config=per_topic_config,
        language_code=lang,
        language_label=language_label,
    )
    base_response["assessment_id"] = assessment_id
    return base_response


def _difficulty_for_topic_practice(
    topic: str,
    profile: dict[str, Any],
) -> str:
    """Current level for improve; stepped level when proficient enough."""
    perf_by_name = {
        t["topic_name"]: t for t in profile.get("topic_performance") or []
    }
    item = perf_by_name.get(topic) or {}
    avg = float(item.get("average_percent") or 0)
    last = _normalize_difficulty(item.get("last_difficulty"))
    recommended = profile.get("recommended_difficulty_by_topic") or {}
    target = _normalize_difficulty(
        recommended.get(topic)
        or employee_profile_service._recommended_difficulty(avg, last)
    )
    if avg >= PROFICIENCY_THRESHOLD_PERCENT and _DIFFICULTY_RANK[target] > _DIFFICULTY_RANK[last]:
        return target
    return last


def _topic_practice_summary(topics: list[str], difficulty_map: dict[str, str]) -> str:
    if not topics:
        return ""
    parts = [f"**{t}** ({difficulty_map.get(t, 'beginner')})" for t in topics]
    return "Practice session on: " + ", ".join(parts) + "."


def create_from_topics_assessment(
    employee_id: str,
    language_code: str,
    topic_names: list[str],
    *,
    questions_requested: int | None = None,
) -> dict[str, Any]:
    """Bank-only practice for explicit topics (heatmap / radar picker)."""
    eid = (employee_id or "").strip()
    if not eid:
        raise ValueError("employee_id is required")
    lang = (language_code or "").strip()
    if not lang:
        raise ValueError("language_code is required")

    selected = _clamp_topic_names(topic_names, max_topics=MAX_TOPICS_PER_SESSION)
    if not selected:
        raise ValueError("At least one topic is required")

    requested = _clamp_questions_requested(questions_requested)
    profile = employee_profile_service.get_employee_profile(
        eid, language_code=lang, scope="full_history"
    )

    base_response = _improvement_base_response(eid, lang, requested)
    base_response["selected_topics"] = selected

    if profile["assessments_analyzed"] == 0:
        base_response["availability_message"] = MSG_NO_HISTORY
        return base_response

    difficulty_map = {
        topic: _difficulty_for_topic_practice(topic, profile) for topic in selected
    }
    base_response["target_difficulty_by_topic"] = difficulty_map
    base_response["topic_summary"] = _topic_practice_summary(selected, difficulty_map)

    per_topic_config = _allocate_per_topic_config(selected, requested)
    rows, _shortage = _build_bank_only_rows(per_topic_config, difficulty_map, eid)
    delivered = len(rows)
    base_response["questions_delivered"] = delivered

    if delivered == 0:
        if _topics_have_bank_questions(selected, difficulty_map):
            base_response["availability_message"] = _all_mastered_message(
                selected, difficulty_map
            )
        else:
            base_response["availability_message"] = MSG_NO_BANK_FOR_TOPICS
        return base_response

    if delivered < requested:
        base_response["availability_message"] = MSG_SHORTAGE_TEMPLATE.format(
            requested=requested,
            delivered=delivered,
        )

    language_label = _resolve_language_label(lang)
    base_response["assessment_id"] = _persist_bank_only_assessment(
        rows,
        topic_names=selected,
        per_topic_config=per_topic_config,
        language_code=lang,
        language_label=language_label,
    )
    return base_response


def _quick_practice_plan(
    report: dict[str, Any],
    profile: dict[str, Any],
) -> tuple[list[str], dict[str, str]]:
    insights = report.get("insights") or {}
    perf = {t["topic_name"]: t for t in profile.get("topic_performance") or []}
    recommended = profile.get("recommended_difficulty_by_topic") or {}
    plans: list[tuple[str, str]] = []

    for topic in (insights.get("unexplored_topics") or [])[:2]:
        plans.append((topic, "beginner"))

    for topic in (insights.get("focus_areas") or [])[:2]:
        item = perf.get(topic) or {}
        last = _normalize_difficulty(item.get("last_difficulty"))
        plans.append((topic, last))

    for topic in (insights.get("strengths") or [])[:2]:
        item = perf.get(topic) or {}
        avg = float(item.get("average_percent") or 0)
        last = _normalize_difficulty(item.get("last_difficulty"))
        target = _normalize_difficulty(
            recommended.get(topic)
            or employee_profile_service._recommended_difficulty(avg, last)
        )
        if _DIFFICULTY_RANK[target] > _DIFFICULTY_RANK[last]:
            plans.append((topic, target))
        else:
            plans.append((topic, last))

    seen: set[str] = set()
    topics: list[str] = []
    difficulty_map: dict[str, str] = {}
    for topic, level in plans:
        if topic in seen:
            continue
        seen.add(topic)
        topics.append(topic)
        difficulty_map[topic] = level
        if len(topics) >= MAX_TOPICS_PER_SESSION:
            break
    return topics, difficulty_map


def create_quick_practice_assessment(
    employee_id: str,
    language_code: str,
    *,
    questions_requested: int | None = None,
) -> dict[str, Any]:
    """One-click practice from report recommendations (default 10 questions)."""
    eid = (employee_id or "").strip()
    if not eid:
        raise ValueError("employee_id is required")
    lang = (language_code or "").strip()
    if not lang:
        raise ValueError("language_code is required")

    requested = _clamp_questions_requested(
        questions_requested
        if questions_requested is not None
        else DEFAULT_QUICK_PRACTICE_QUESTIONS
    )

    report = employee_profile_service.get_employee_report(
        eid, language_code=lang, period="all_time"
    )
    profile = employee_profile_service.get_employee_profile(
        eid, language_code=lang, scope="full_history"
    )

    base_response = _improvement_base_response(eid, lang, requested)
    selected, difficulty_map = _quick_practice_plan(report, profile)
    base_response["selected_topics"] = selected
    base_response["target_difficulty_by_topic"] = difficulty_map

    if not selected:
        base_response["availability_message"] = (
            "No quick-practice topics available from your report yet."
        )
        return base_response

    base_response["topic_summary"] = _topic_practice_summary(selected, difficulty_map)
    per_topic_config = _allocate_per_topic_config(selected, requested)
    rows, _shortage = _build_bank_only_rows(per_topic_config, difficulty_map, eid)
    delivered = len(rows)
    base_response["questions_delivered"] = delivered

    if delivered == 0:
        base_response["availability_message"] = MSG_NO_BANK_FOR_TOPICS
        return base_response

    if delivered < requested:
        base_response["availability_message"] = MSG_SHORTAGE_TEMPLATE.format(
            requested=requested,
            delivered=delivered,
        )

    language_label = _resolve_language_label(lang)
    base_response["assessment_id"] = _persist_bank_only_assessment(
        rows,
        topic_names=selected,
        per_topic_config=per_topic_config,
        language_code=lang,
        language_label=language_label,
    )
    return base_response
