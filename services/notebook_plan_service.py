"""
Notebook expectation and template eligibility for assessments.

Notebook UI and downloads are driven by jupyter-topic *coding* counts,
not merely routing_flag === "mixed" or the presence of jupyter catalog topics.
"""

from __future__ import annotations

from typing import Any

from services import db_service


def derive_per_topic_config(
    topic_names: list[str],
    types: list[str],
    questions_per_type: dict[str, int],
) -> dict[str, dict[str, int]]:
    """
    Split global per-type counts evenly across catalog topics (auto allocation).
    Example: 4 topics, {mcq: 4, coding: 4} → each topic {mcq: 1, coding: 1}.
    """
    names = [n.strip() for n in topic_names if n and str(n).strip()]
    if not names:
        return {}

    n = len(names)
    result: dict[str, dict[str, int]] = {t: {} for t in names}

    for qtype in types:
        total = int(questions_per_type.get(qtype, 0) or 0)
        if total <= 0:
            continue
        base, remainder = divmod(total, n)
        for i, tname in enumerate(names):
            count = base + (1 if i < remainder else 0)
            if count > 0:
                result[tname][qtype] = count

    return result


def jupyter_topic_names_from_list(topic_names: list[str]) -> list[str]:
    """Catalog topic names that use jupyter modality among the given list."""
    names = [n.strip() for n in topic_names if n and str(n).strip()]
    if not names:
        return []
    modality_by_name = db_service.get_topic_modality_by_names(names)
    return [t for t in names if modality_by_name.get(t) == "jupyter"]


def expected_notebook_coding_from_config(
    per_topic_config: dict[str, dict[str, int]],
    jupyter_topic_names: list[str],
) -> int:
    """Sum of coding counts configured for jupyter-modality topics only."""
    jupyter_set = set(jupyter_topic_names)
    total = 0
    for tname, cfg in per_topic_config.items():
        if tname in jupyter_set:
            total += int(cfg.get("coding", 0) or 0)
    return total


def resolve_question_modality(
    topic_name: str,
    jupyter_topic_names: set[str],
    modality_by_name: dict[str, str],
) -> str | None:
    """Return 'jupyter', 'pyodide', or None (legacy untagged)."""
    tname = (topic_name or "").strip()
    if not tname:
        return None
    if tname in jupyter_topic_names or modality_by_name.get(tname) == "jupyter":
        return "jupyter"
    return "pyodide"


def count_notebook_coding_in_rows(
    rows: list[dict[str, Any]],
    *,
    jupyter_topic_names: list[str] | None = None,
    routing_flag: str = "pyodide",
) -> int:
    """Count coding rows that belong in the notebook template."""
    jupyter_set = set(jupyter_topic_names or [])
    topic_names_on_questions = list(
        dict.fromkeys((r.get("topic_name") or "").strip() for r in rows if r.get("topic_name"))
    )
    modality_by_name = db_service.get_topic_modality_by_names(topic_names_on_questions)

    count = 0
    for r in rows:
        if (r.get("type") or "").lower() != "coding":
            continue
        tname = (r.get("topic_name") or "").strip()
        if resolve_question_modality(tname, jupyter_set, modality_by_name) == "jupyter":
            count += 1

    if count == 0 and routing_flag == "jupyter":
        return sum(1 for r in rows if (r.get("type") or "").lower() == "coding")

    return count


def notebook_plan_from_rows(
    rows: list[dict[str, Any]],
    *,
    topic_names: list[str],
    per_topic_config: dict[str, dict[str, int]],
    routing_flag: str = "pyodide",
) -> dict[str, Any]:
    """Build notebook plan from generated rows (before or after persist)."""
    jupyter_topics = jupyter_topic_names_from_list(topic_names)
    expected = expected_notebook_coding_from_config(per_topic_config, jupyter_topics)
    actual = count_notebook_coding_in_rows(
        rows,
        jupyter_topic_names=jupyter_topics,
        routing_flag=routing_flag,
    )
    return _plan_dict(
        routing_flag=routing_flag,
        jupyter_topic_names=jupyter_topics,
        expected=expected,
        actual=actual,
    )


def per_topic_config_from_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Reconstruct per-topic type counts from stored question rows."""
    cfg: dict[str, dict[str, int]] = {}
    for r in rows:
        tname = (r.get("topic_name") or "").strip()
        if not tname:
            continue
        qtype = (r.get("type") or "").lower()
        if not qtype:
            continue
        cfg.setdefault(tname, {})
        cfg[tname][qtype] = cfg[tname].get(qtype, 0) + 1
    return cfg


def notebook_plan_for_assessment(assessment_id: str) -> dict[str, Any]:
    """Notebook plan for a persisted assessment (participant / template endpoints)."""
    meta = db_service.get_assessment_metadata(assessment_id)
    rows = db_service.read_questions_by_assessment(assessment_id)
    jupyter_topics = list(meta.get("jupyter_topic_names") or [])
    routing_flag = meta.get("routing_flag") or "pyodide"
    per_topic_config = per_topic_config_from_rows(rows)
    expected = expected_notebook_coding_from_config(per_topic_config, jupyter_topics)
    actual = count_notebook_coding_in_rows(
        rows,
        jupyter_topic_names=jupyter_topics,
        routing_flag=routing_flag,
    )
    return _plan_dict(
        routing_flag=routing_flag,
        jupyter_topic_names=jupyter_topics,
        expected=expected,
        actual=actual,
    )


def _plan_dict(
    *,
    routing_flag: str,
    jupyter_topic_names: list[str],
    expected: int,
    actual: int,
) -> dict[str, Any]:
    notebook_expected = expected > 0
    notebook_ready = actual > 0
    return {
        "routing_flag": routing_flag,
        "jupyter_topic_names": jupyter_topic_names,
        "expected_notebook_coding_count": expected,
        "actual_notebook_coding_count": actual,
        "notebook_expected": notebook_expected,
        "notebook_ready": notebook_ready,
        "is_consistent": (not notebook_expected) or (actual > 0),
    }


def validate_notebook_plan_after_generation(plan: dict[str, Any]) -> None:
    """
    Raise ValueError if coding was configured for jupyter topics but none were stored.
    When expected == 0, no notebook is required (valid).
    """
    expected = int(plan.get("expected_notebook_coding_count", 0) or 0)
    actual = int(plan.get("actual_notebook_coding_count", 0) or 0)
    if expected > 0 and actual == 0:
        raise ValueError(
            "This assessment assigns coding questions to jupyter topics, but none were "
            "generated for the notebook. Adjust topic or type counts and regenerate."
        )
