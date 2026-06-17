"""
Cross-assessment employee performance profile and shippable stats report (Stage 4).

Powers future “Help me improve” flows and the employee report UI.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from services import catalog_service, db_service, report_service
from services.attempt_service import get_attempt_timing
from services.question_bank_service import get_employee_mastered_bank_ids
from services.report_service import _parse_participant_name

Scope = Literal["last_3", "full_history"]
Period = Literal["all_time", "last_90_days"]

WEAK_THRESHOLD = 70.0
STRENGTH_THRESHOLD = 80.0
STRENGTH_MIN_QUESTIONS = 5
SCORE_CORRECT_THRESHOLD = 70.0

REPORT_VERSION = "1.0"

_TIER_TOPIC_RE = re.compile(r"^Tier\s*(\d+)", re.IGNORECASE)

# Common assessment labels → catalog ``languages.code`` (seed uses ``py`` for Python).
_LANGUAGE_CODE_ALIASES: dict[str, str] = {
    "python": "py",
    "javascript": "js",
    "nodejs": "js",
    "node": "js",
    "node.js": "js",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _normalize_lang(code: str | None) -> str | None:
    s = (code or "").strip().casefold()
    return s or None


def _resolve_catalog_language_code(
    code: str | None,
    *,
    language_label: str | None = None,
) -> str | None:
    """
    Map assessment ``language_code`` / label to catalog ``languages.code``.

    Handles ``python`` → ``py`` and name-based fallbacks so unexplored topics
    resolve against the full catalog (Tier 1 + Tier 2 + …).
    """
    norm = _normalize_lang(code)
    label_norm = _normalize_lang(language_label)
    languages = catalog_service.list_languages()

    candidates: list[str] = []
    if norm:
        candidates.append(_LANGUAGE_CODE_ALIASES.get(norm, norm))
    if label_norm:
        candidates.append(_LANGUAGE_CODE_ALIASES.get(label_norm, label_norm))

    for cand in candidates:
        for lang in languages:
            lc = _normalize_lang(lang.get("code"))
            if lc == cand:
                return lc

    if norm:
        for lang in languages:
            lc = _normalize_lang(lang.get("code"))
            name = _normalize_lang(lang.get("name"))
            if norm == name or (name and norm in name):
                return lc
    if label_norm:
        for lang in languages:
            lc = _normalize_lang(lang.get("code"))
            name = _normalize_lang(lang.get("name"))
            if label_norm == name or (name and label_norm in name):
                return lc

    return candidates[0] if candidates else None


def _topic_tier_number(topic_name: str) -> int:
    m = _TIER_TOPIC_RE.match((topic_name or "").strip())
    return int(m.group(1)) if m else 999


def _sort_unexplored_topic_names(names: list[str]) -> list[str]:
    """Tier 1, then Tier 2, … — full catalog gaps, not alphabetical Tier-1-only."""
    return sorted(names, key=lambda n: (_topic_tier_number(n), n.casefold()))


def _pick_unexplored_for_recommendations(
    unexplored: list[str],
    *,
    limit: int = 3,
) -> list[str]:
    """Prefer higher tiers (e.g. Tier 2) when suggesting areas to explore."""
    sorted_names = _sort_unexplored_topic_names(unexplored)
    by_tier: dict[int, list[str]] = defaultdict(list)
    for name in sorted_names:
        by_tier[_topic_tier_number(name)].append(name)

    picked: list[str] = []
    for tier in sorted(by_tier.keys(), reverse=True):
        for name in by_tier[tier]:
            if len(picked) >= limit:
                return picked
            picked.append(name)
    return picked


def proficiency_label(avg_percent: float) -> str:
    """Legacy score-band label (Beginner/Intermediate/Advanced). Prefer level_progress_label."""
    if avg_percent >= 75:
        return "Advanced"
    if avg_percent >= 50:
        return "Intermediate"
    return "Beginner"


_DIFFICULTY_RANK = {"beginner": 1, "intermediate": 2, "advanced": 3}


def _highest_difficulty(levels: list[str | None]) -> str:
    best = "beginner"
    for raw in levels:
        d = (raw or "beginner").strip().lower()
        if d not in _DIFFICULTY_RANK:
            d = "beginner"
        if _DIFFICULTY_RANK[d] > _DIFFICULTY_RANK[best]:
            best = d
    return best


def assessed_level_from_records(records: list[dict[str, Any]]) -> str:
    """Highest difficulty tier the employee has actually been assessed at."""
    levels: list[str | None] = []
    for rec in records:
        levels.extend((rec.get("topic_difficulty") or {}).values())
    return _highest_difficulty(levels)


def format_assessed_level_label(level: str) -> str:
    d = (level or "beginner").strip().lower()
    if d not in _DIFFICULTY_RANK:
        d = "beginner"
    return d.capitalize()


def level_progress_label(avg_percent: float, assessed_level: str) -> str:
    """
    Progress wording within the employee's assessed difficulty — not the next tier.

    Examples at beginner: ~40% → needs improvement; ~68% → on the right path;
    ~90% → conquered beginner, ready to step up.
    """
    level = (assessed_level or "beginner").strip().lower()
    if level not in _DIFFICULTY_RANK:
        level = "beginner"

    if avg_percent < 50:
        return "Needs improvement"
    if avg_percent < 75:
        return "You're on the right path"
    if level == "advanced":
        return "You've conquered this level — excellent mastery!"
    return "You've conquered this level — ready for the next!"


def _recommended_difficulty(avg_percent: float, last_difficulty: str | None) -> str:
    last = (last_difficulty or "beginner").strip().lower()
    if last not in ("beginner", "intermediate", "advanced"):
        last = "beginner"
    if last == "beginner" and avg_percent >= 75:
        return "intermediate"
    if last == "intermediate" and avg_percent >= 80:
        return "advanced"
    return last


def _trend_from_series(values: list[float]) -> str | None:
    if len(values) < 2:
        return None
    prev, latest = values[-2], values[-1]
    if latest > prev + 2:
        return "up"
    if latest < prev - 2:
        return "down"
    return "flat"


def _assessment_duration_seconds(
    assessment_id: str,
    employee_id: str,
    *,
    submitted_at: str,
    earliest_timestamp: str,
) -> int:
    timing = get_attempt_timing(assessment_id, employee_id)
    if timing and timing.get("started_at"):
        end = timing.get("submitted_at") or submitted_at
        start_dt = _parse_iso(timing["started_at"])
        end_dt = _parse_iso(end or "")
        if start_dt and end_dt and end_dt >= start_dt:
            return max(0, int((end_dt - start_dt).total_seconds()))
    start_dt = _parse_iso(earliest_timestamp)
    end_dt = _parse_iso(submitted_at)
    if start_dt and end_dt and end_dt >= start_dt:
        return max(0, int((end_dt - start_dt).total_seconds()))
    return 0


def _filter_by_period(
    records: list[dict[str, Any]], period: Period
) -> list[dict[str, Any]]:
    if period != "last_90_days":
        return records
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    out: list[dict[str, Any]] = []
    for rec in records:
        dt = _parse_iso(str(rec.get("submitted_at") or ""))
        if dt and dt >= cutoff:
            out.append(rec)
    return out


def _filter_by_language(
    records: list[dict[str, Any]], language_code: str | None
) -> list[dict[str, Any]]:
    lang = _normalize_lang(language_code)
    if not lang:
        return records
    return [
        r
        for r in records
        if _normalize_lang(r.get("language_code")) == lang
    ]


def _load_assessment_records(
    employee_id: str,
    *,
    language_code: str | None = None,
    period: Period = "all_time",
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Build per-assessment report snapshots, newest first."""
    eid = (employee_id or "").strip()
    if not eid:
        return []

    summaries = db_service.list_employee_completed_assessments(eid)
    summaries = _filter_by_period(summaries, period)

    records: list[dict[str, Any]] = []
    for row in summaries:
        aid = row["assessment_id"]
        meta = db_service.get_assessment_metadata(aid)
        lang = _resolve_catalog_language_code(
            meta.get("language_code"),
            language_label=meta.get("language_label"),
        )
        if language_code:
            filter_lang = _resolve_catalog_language_code(language_code)
            if filter_lang != lang:
                continue
        try:
            report = report_service.build_report(aid, eid)
        except ValueError:
            continue

        qrows = db_service.read_questions_by_assessment(aid)
        diff_by_qid = {
            str(q["question_id"]): (q.get("difficulty") or "").strip().lower() or None
            for q in qrows
        }
        topic_diff: dict[str, str | None] = {}
        for q in qrows:
            tname = (q.get("topic_name") or "").strip() or "General"
            diff = (q.get("difficulty") or "").strip().lower() or None
            if tname not in topic_diff and diff:
                topic_diff[tname] = diff

        duration = _assessment_duration_seconds(
            aid,
            eid,
            submitted_at=str(row.get("submitted_at") or report.get("submitted_at") or ""),
            earliest_timestamp=str(row.get("earliest_timestamp") or ""),
        )

        records.append(
            {
                "assessment_id": aid,
                "submitted_at": report.get("submitted_at") or row.get("submitted_at"),
                "language_code": lang,
                "language_label": (meta.get("language_label") or lang or "").strip(),
                "overall_score": float(report.get("overall_score") or 0),
                "report": report,
                "difficulty_by_question": diff_by_qid,
                "topic_difficulty": topic_diff,
                "duration_seconds": duration,
                "display_name": _parse_participant_name(report["participant"]["user_id"]),
            }
        )

    if limit is not None:
        records = records[:limit]
    return records


def _merge_topic_performance(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """
    Merge topic stats across assessments (chronological order for sparklines).
    Returns (topic_performance list, last_difficulty_by_topic).
    """
    chronological = list(reversed(records))
    scores_by_topic: dict[str, list[float]] = defaultdict(list)
    attempts_by_topic: dict[str, int] = defaultdict(int)
    sparkline_by_topic: dict[str, list[float]] = defaultdict(list)
    last_difficulty: dict[str, str | None] = {}

    for rec in chronological:
        report = rec["report"]
        topics_in_assessment: set[str] = set()
        per_topic_scores: dict[str, list[float]] = defaultdict(list)
        for q in report.get("questions") or []:
            topic = (q.get("topic_name") or "").strip() or "General"
            topics_in_assessment.add(topic)
            per_topic_scores[topic].append(float(q.get("score") or 0))

        for topic, scores in per_topic_scores.items():
            scores_by_topic[topic].extend(scores)
            attempts_by_topic[topic] += 1
            sparkline_by_topic[topic].append(
                round(sum(scores) / len(scores), 2) if scores else 0.0
            )
            diff = (rec.get("topic_difficulty") or {}).get(topic)
            if diff:
                last_difficulty[topic] = diff

    topic_performance: list[dict[str, Any]] = []
    for topic in sorted(scores_by_topic.keys()):
        scores = scores_by_topic[topic]
        avg = round(sum(scores) / len(scores), 2) if scores else 0.0
        spark = sparkline_by_topic[topic][-5:]
        topic_performance.append(
            {
                "topic_name": topic,
                "questions_count": len(scores),
                "average_percent": avg,
                "attempts": attempts_by_topic[topic],
                "last_difficulty": last_difficulty.get(topic),
                "trend": _trend_from_series(spark),
                "sparkline": spark,
            }
        )

    topic_performance.sort(key=lambda x: x["average_percent"])
    return topic_performance, {k: v or "beginner" for k, v in last_difficulty.items()}


def _catalog_topic_names(language_code: str | None) -> list[str]:
    resolved = _resolve_catalog_language_code(language_code)
    languages = catalog_service.list_languages()
    if resolved:
        languages = [
            l for l in languages if _normalize_lang(l.get("code")) == resolved
        ]
    names: list[str] = []
    for lang in languages:
        for topic in catalog_service.list_topics(language_id=lang["id"]):
            name = (topic.get("name") or "").strip()
            if name:
                names.append(name)
    return sorted(set(names))


def _explored_topic_names(records: list[dict[str, Any]]) -> list[str]:
    explored: set[str] = set()
    for rec in records:
        for q in (rec.get("report") or {}).get("questions") or []:
            t = (q.get("topic_name") or "").strip()
            if t:
                explored.add(t)
    return sorted(explored)


def _explored_topic_names_by_language(
    records: list[dict[str, Any]],
) -> dict[str, set[str]]:
    """Topics attempted, grouped by assessment language_code."""
    by_lang: dict[str, set[str]] = defaultdict(set)
    for rec in records:
        lang = _resolve_catalog_language_code(
            rec.get("language_code"),
            language_label=rec.get("language_label"),
        ) or _normalize_lang(rec.get("language_code"))
        if not lang:
            continue
        for q in (rec.get("report") or {}).get("questions") or []:
            t = (q.get("topic_name") or "").strip()
            if t:
                by_lang[lang].add(t)
    return by_lang


def _evaluated_language_codes(records: list[dict[str, Any]]) -> set[str]:
    codes: set[str] = set()
    for rec in records:
        lang = _resolve_catalog_language_code(
            rec.get("language_code"),
            language_label=rec.get("language_label"),
        ) or _normalize_lang(rec.get("language_code"))
        if lang:
            codes.add(lang)
    return codes


def _unexplored_topic_names(
    records: list[dict[str, Any]],
    *,
    language_code: str | None = None,
) -> list[str]:
    """
    Catalog topics not yet attempted by this employee.

    When no ``language_code`` filter is passed, only languages the employee
    has been assessed in are considered (e.g. Python only — not Java).
    """
    explored_by_lang = _explored_topic_names_by_language(records)
    lang_filter = _resolve_catalog_language_code(language_code) if language_code else None

    if lang_filter:
        catalog = set(_catalog_topic_names(lang_filter))
        resolved = _resolve_catalog_language_code(lang_filter) or lang_filter
        explored = explored_by_lang.get(resolved, set())
        for key, topics in explored_by_lang.items():
            if _resolve_catalog_language_code(key) == resolved:
                explored |= topics
        return _sort_unexplored_topic_names(sorted(catalog - explored))

    unexplored: set[str] = set()
    for lang in _evaluated_language_codes(records):
        resolved = _resolve_catalog_language_code(lang) or lang
        catalog = set(_catalog_topic_names(resolved))
        explored = explored_by_lang.get(lang, set())
        if resolved != lang:
            explored |= explored_by_lang.get(resolved, set())
        unexplored |= catalog - explored
    return _sort_unexplored_topic_names(sorted(unexplored))


def get_employee_profile(
    employee_id: str,
    *,
    language_code: str | None = None,
    scope: Scope = "last_3",
) -> dict[str, Any]:
    """
    Cross-assessment profile for improvement flows.

    ``scope=last_3`` — weak areas (last 3 distinct assessments only).
    ``scope=full_history`` — new areas + difficulty step-up.
    """
    eid = (employee_id or "").strip()
    if not eid:
        raise ValueError("employee_id is required")

    all_records = _load_assessment_records(eid, language_code=language_code)
    if scope == "last_3":
        records = all_records[:3]
    else:
        records = all_records

    topic_performance, last_difficulty = _merge_topic_performance(records)
    explored = _explored_topic_names(all_records if scope == "full_history" else records)
    history_for_unexplored = all_records
    unexplored = _unexplored_topic_names(
        history_for_unexplored,
        language_code=language_code,
    )

    weakest = [
        t["topic_name"]
        for t in topic_performance
        if t["average_percent"] < WEAK_THRESHOLD
    ]
    weakest.sort(key=lambda name: next(
        (x["average_percent"] for x in topic_performance if x["topic_name"] == name), 0
    ))

    recommended: dict[str, str] = {}
    if scope == "full_history":
        for item in topic_performance:
            recommended[item["topic_name"]] = _recommended_difficulty(
                item["average_percent"],
                last_difficulty.get(item["topic_name"]),
            )

    return {
        "employee_id": eid,
        "scope": scope,
        "assessments_analyzed": len(records),
        "language_code": language_code,
        "topic_performance": topic_performance,
        "explored_topic_names": explored,
        "unexplored_topic_names": unexplored,
        "weakest_topics": weakest,
        "recommended_difficulty_by_topic": recommended,
    }


def _language_sections(
    records: list[dict[str, Any]],
    mastered_by_topic: dict[str, int],
) -> list[dict[str, Any]]:
    by_lang: dict[str, dict[str, Any]] = {}
    chronological = list(reversed(records))

    for rec in chronological:
        code = _normalize_lang(rec.get("language_code")) or "unknown"
        label = (rec.get("language_label") or code or "Unknown").strip()
        if code not in by_lang:
            by_lang[code] = {
                "language_code": code,
                "language_label": label,
                "scores": [],
                "topic_scores": defaultdict(list),
                "topic_sparklines": defaultdict(list),
                "topic_difficulty": {},
                "topics_seen": set(),
            }
        bucket = by_lang[code]
        report = rec["report"]
        for q in report.get("questions") or []:
            topic = (q.get("topic_name") or "").strip() or "General"
            score = float(q.get("score") or 0)
            bucket["scores"].append(score)
            bucket["topic_scores"][topic].append(score)
            bucket["topics_seen"].add(topic)
            diff = (rec.get("topic_difficulty") or {}).get(topic)
            if diff:
                bucket["topic_difficulty"][topic] = diff

        per_topic_avg: dict[str, float] = {}
        for q in report.get("questions") or []:
            topic = (q.get("topic_name") or "").strip() or "General"
            scores = [
                float(x.get("score") or 0)
                for x in report.get("questions") or []
                if ((x.get("topic_name") or "").strip() or "General") == topic
            ]
            if scores:
                per_topic_avg[topic] = round(sum(scores) / len(scores), 2)
        for topic, avg in per_topic_avg.items():
            bucket["topic_sparklines"][topic].append(avg)

    sections: list[dict[str, Any]] = []
    for code in sorted(by_lang.keys()):
        bucket = by_lang[code]
        scores = bucket["scores"]
        overall = round(sum(scores) / len(scores), 2) if scores else 0.0
        catalog_count = len(_catalog_topic_names(code if code != "unknown" else None))
        topics_seen = bucket["topics_seen"]
        topic_items: list[dict[str, Any]] = []
        for topic in sorted(topics_seen):
            tscores = bucket["topic_scores"][topic]
            avg = round(sum(tscores) / len(tscores), 2) if tscores else 0.0
            spark = bucket["topic_sparklines"][topic][-5:]
            topic_items.append(
                {
                    "topic_name": topic,
                    "questions_count": len(tscores),
                    "mastered_count": mastered_by_topic.get(topic, 0),
                    "percent_correct": avg,
                    "last_difficulty": bucket["topic_difficulty"].get(topic),
                    "trend": _trend_from_series(spark),
                    "sparkline": spark,
                }
            )
        topic_items.sort(key=lambda x: x["percent_correct"])
        lang_level = _highest_difficulty(list(bucket["topic_difficulty"].values()))
        sections.append(
            {
                "language_code": code,
                "language_label": bucket["language_label"],
                "topics_covered": len(topics_seen),
                "topics_in_catalog": catalog_count,
                "questions_count": len(scores),
                "percent_correct": overall,
                "assessed_level_label": format_assessed_level_label(lang_level),
                "proficiency_label": level_progress_label(overall, lang_level),
                "topics": topic_items,
            }
        )
    return sections


def _question_type_breakdown(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_type: dict[str, list[float]] = defaultdict(list)
    for rec in records:
        for q in (rec.get("report") or {}).get("questions") or []:
            qtype = (q.get("type") or "unknown").strip().lower()
            by_type[qtype].append(float(q.get("score") or 0))
    out: dict[str, dict[str, Any]] = {}
    for qtype, scores in by_type.items():
        avg = round(sum(scores) / len(scores), 2) if scores else 0.0
        out[qtype] = {"count": len(scores), "percent_correct": avg}
    return out


def _cumulative_progress(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chronological = list(reversed(records))
    correct = 0
    wrong = 0
    points: list[dict[str, Any]] = []
    for rec in chronological:
        for q in (rec.get("report") or {}).get("questions") or []:
            score = float(q.get("score") or 0)
            if q.get("correct") or score >= SCORE_CORRECT_THRESHOLD:
                correct += 1
            else:
                wrong += 1
        points.append(
            {
                "submitted_at": rec.get("submitted_at") or "",
                "cumulative_correct": correct,
                "cumulative_wrong": wrong,
            }
        )
    return points


def _radar_topics(records: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    if not records:
        return []
    latest = records[0]
    rolling = records[:3]
    latest_by_topic: dict[str, list[float]] = defaultdict(list)
    rolling_by_topic: dict[str, list[float]] = defaultdict(list)

    for q in (latest.get("report") or {}).get("questions") or []:
        topic = (q.get("topic_name") or "").strip() or "General"
        latest_by_topic[topic].append(float(q.get("score") or 0))

    for rec in rolling:
        per_topic: dict[str, list[float]] = defaultdict(list)
        for q in (rec.get("report") or {}).get("questions") or []:
            topic = (q.get("topic_name") or "").strip() or "General"
            per_topic[topic].append(float(q.get("score") or 0))
        for topic, scores in per_topic.items():
            rolling_by_topic[topic].append(
                round(sum(scores) / len(scores), 2) if scores else 0.0
            )

    topics = sorted(set(latest_by_topic.keys()) | set(rolling_by_topic.keys()))
    out: list[dict[str, Any]] = []
    for topic in topics[:limit]:
        lscores = latest_by_topic[topic]
        latest_avg = round(sum(lscores) / len(lscores), 2) if lscores else 0.0
        rvals = rolling_by_topic[topic]
        rolling_avg = round(sum(rvals) / len(rvals), 2) if rvals else latest_avg
        out.append(
            {
                "topic_name": topic,
                "latest_percent": latest_avg,
                "rolling_avg_percent": rolling_avg,
            }
        )
    return out


def _build_insights(
    records: list[dict[str, Any]],
    topic_performance: list[dict[str, Any]],
    unexplored: list[str],
) -> dict[str, Any]:
    strengths = [
        t["topic_name"]
        for t in topic_performance
        if t["average_percent"] >= STRENGTH_THRESHOLD
        and t["questions_count"] >= STRENGTH_MIN_QUESTIONS
    ]
    strengths.sort(
        key=lambda name: next(
            (x["average_percent"] for x in topic_performance if x["topic_name"] == name),
            0,
        ),
        reverse=True,
    )
    strengths = strengths[:3]

    last3_perf, _ = _merge_topic_performance(records[:3])
    focus_areas = [
        t["topic_name"]
        for t in last3_perf
        if t["average_percent"] < WEAK_THRESHOLD
    ]

    recommendations: list[str] = []
    for topic in focus_areas[:3]:
        recommendations.append(
            f"Extra practice on {topic} — scores in your last 3 assessments are below {WEAK_THRESHOLD:.0f}%."
        )
    for topic in _pick_unexplored_for_recommendations(unexplored, limit=2):
        recommendations.append(
            f"Explore {topic} — not yet covered in your assessment history."
        )
    if strengths:
        recommendations.append(
            f"Keep momentum in {', '.join(strengths[:2])} while addressing weaker areas."
        )

    return {
        "strengths": strengths,
        "focus_areas": focus_areas,
        "unexplored_topics": unexplored,
        "recommendations": recommendations,
    }


def get_employee_report(
    employee_id: str,
    *,
    language_code: str | None = None,
    period: Period = "all_time",
) -> dict[str, Any]:
    """Full shippable stats report for one employee."""
    eid = (employee_id or "").strip()
    if not eid:
        raise ValueError("employee_id is required")

    records = _load_assessment_records(eid, language_code=language_code, period=period)
    mastered_ids = get_employee_mastered_bank_ids(eid)
    mastered_by_topic = db_service.count_employee_mastered_by_topic(eid)
    needs_practice = db_service.count_employee_needs_practice_bank_questions(eid)

    all_scores: list[float] = []
    total_time = 0
    display_name = ""
    for rec in records:
        report = rec["report"]
        if not display_name:
            display_name = rec.get("display_name") or ""
        total_time += int(rec.get("duration_seconds") or 0)
        for q in report.get("questions") or []:
            all_scores.append(float(q.get("score") or 0))

    overall = round(sum(all_scores) / len(all_scores), 2) if all_scores else 0.0
    assessments_n = len(records)
    avg_time = int(total_time / assessments_n) if assessments_n else 0

    topic_performance, _ = _merge_topic_performance(records)
    unexplored = _unexplored_topic_names(records, language_code=language_code)

    timeline = [
        {
            "assessment_id": rec["assessment_id"],
            "submitted_at": rec.get("submitted_at") or "",
            "percent": round(float(rec.get("overall_score") or 0), 2),
            "language_code": rec.get("language_code"),
        }
        for rec in reversed(records)
    ]

    insights = _build_insights(records, topic_performance, unexplored)

    assessed_level = assessed_level_from_records(records)

    return {
        "title": "Skills Progress Report",
        "report_version": REPORT_VERSION,
        "employee_id": eid,
        "display_name": display_name,
        "period": period,
        "report_generated_at": _utc_now_iso(),
        "scope": "full_history",
        "summary": {
            "assessments_completed": assessments_n,
            "questions_answered": len(all_scores),
            "overall_percent_correct": overall,
            "assessed_level_label": format_assessed_level_label(assessed_level),
            "proficiency_label": level_progress_label(overall, assessed_level),
            "total_time_seconds": total_time,
            "avg_assessment_time_seconds": avg_time,
        },
        "languages": _language_sections(records, mastered_by_topic),
        "score_timeline": timeline,
        "question_type_breakdown": _question_type_breakdown(records),
        "mastery": {
            "mastered_count": len(mastered_ids),
            "needs_practice_count": needs_practice,
        },
        "insights": insights,
        "radar_topics": _radar_topics(records),
        "cumulative_progress": _cumulative_progress(records),
    }
