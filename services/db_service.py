"""
MongoDB persistence for assessments and submissions.

This module is the **low-level data access layer** for everything stored in
MongoDB related to assessments, questions, and participant answers. Higher-level
orchestration (LLM calls, grading, reports) lives in ``assessment_service``,
``report_service``, and ``employee_profile_service`` — those modules call into
here for reads and writes.

Collections touched:
  - ``assessments`` — one document per assessment (metadata, timing, certificates)
  - ``assessment_questions`` — question rows for an assessment
  - ``submissions`` — one row per answered question (or notebook upload)
  - ``assessment_attempts`` — timed-assessment deadlines (deleted on assessment delete)
  - ``topics`` / ``languages`` — read-only catalog lookups
  - ``question_bank`` / ``employee_question_mastery`` — analytics helpers only
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

from services.database import coll, next_id
from services.ids import sanitize_client_id
from services.models import Document

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
    "list_employee_completed_assessments",
    "count_employee_mastered_by_topic",
    "count_employee_needs_practice_bank_questions",
    "save_submission_row",
    "get_topics_by_names",
    "update_assessment_question",
    "get_topic_coding_editor_by_names",
]

# Field-length caps — keep aligned with API validation and Mongo document shape.
_MAX_LANGUAGE_CODE = 32
_MAX_LANGUAGE_LABEL = 256
_MAX_TOPIC_NAME = 512
_MAX_TOPIC_NAME_STORED = 1024
_MAX_TOPIC_NAMES_PER_ASSESSMENT = 50
_MAX_TOPIC_NAMES_COERCE = 80
_NOTEBOOK_QUESTION_ID = "notebook"


def _normalize_language_code(language_code: str | None) -> str | None:
    """Trim and cap catalog language ``code`` (e.g. ``py``) for storage/display."""
    s = (language_code or "").strip()
    return s[:_MAX_LANGUAGE_CODE] if s else None


def _normalize_language_label(language_label: str | None) -> str | None:
    """Trim and cap human-readable language label (e.g. ``Python``) from the admin UI."""
    s = (language_label or "").strip()
    return s[:_MAX_LANGUAGE_LABEL] if s else None


def _normalize_topic_names(names: list[str] | None) -> list[str]:
    """
    Sanitize topic name list before writing to an assessment document.

    Used by ``save_assessment_rows`` and ``save_shared_assessment_rows`` so we
    never persist unbounded lists or oversized strings from the API.
    """
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
    """
    Normalize ``topic_names`` read back from Mongo into a list of strings.

    Historical data may store JSON as a string, a bare list, or a dict wrapper.
    Called when building admin summaries and ``get_assessment_metadata`` so
    callers always receive a consistent ``list[str]``.
    """
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
    """Current UTC timestamp as ISO-8601 string for ``created_at`` fields."""
    return datetime.now(timezone.utc).isoformat()


def _created_at_sort_key(row: dict[str, Any]) -> tuple[int, str]:
    """
    Sort key for ``list_assessments_summary``: newest ``created_at`` first.

    Rows without a parseable timestamp sort last (tuple prefix ``0``).
    """
    raw = (row.get("created_at") or "").strip()
    if not raw:
        return (0, "")
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return (1, dt.astimezone(timezone.utc).isoformat())
    except ValueError:
        return (0, raw)


def _assessment_doc(assessment_id: str) -> dict[str, Any] | None:
    """
    Fetch the raw ``assessments`` document by string ``assessment_id``.

    Internal helper used by most single-assessment lookups in this module.
    """
    return coll("assessments").find_one({"assessment_id": assessment_id.strip()})


def _question_doc(row: dict[str, Any], assessment_id: str) -> dict[str, Any]:
    """
    Build one ``assessment_questions`` document from an in-memory question dict.

    Assigns a monotonic integer ``id`` via ``next_id`` for stable sort order.
    Called by ``save_assessment_rows`` / ``save_shared_assessment_rows`` when
    replacing all questions for an assessment.
    """
    return {
        "id": next_id("assessment_questions"),
        "assessment_id": assessment_id,
        "question_id": str(row["question_id"]),
        "question": row["question"],
        "type": row["type"],
        "options": row.get("options", "") or "",
        "correct_answer": row.get("correct_answer", "") or "",
        "topic_name": str(row.get("topic_name") or ""),
        "code_snippet": row.get("code_snippet") or None,
        "bank_question_id": row.get("bank_question_id"),
        "difficulty": row.get("difficulty"),
        "sample_test_cases": row.get("sample_test_cases"),
        "coding_hint": row.get("coding_hint") or None,
    }


def register_assessment(assessment_id: str, safe_client_id: str) -> None:
    """
    Ensure an ``assessments`` row exists and set ``owner_client_id``.

    Legacy/registry path: creates a stub assessment if missing, or updates the
    owner on an existing row. Most new assessments are created via
    ``save_shared_assessment_rows`` instead; this remains for client-scoped flows
    that register an id before questions are saved.
    """
    aid = assessment_id.strip()
    existing = _assessment_doc(aid)
    if existing:
        coll("assessments").update_one(
            {"assessment_id": aid},
            {"$set": {"owner_client_id": safe_client_id}},
        )
    else:
        coll("assessments").insert_one(
            {
                "assessment_id": aid,
                "owner_client_id": safe_client_id,
                "topic_names": [],
                "created_at": _utc_now_iso(),
            }
        )


def get_client_for_assessment(assessment_id: str) -> str | None:
    """
    Return ``owner_client_id`` for an assessment, or ``None`` if shared.

    ``None`` means any client may access the assessment (see
    ``client_may_access_assessment``). Used internally by access checks and
    admin list summaries (displayed as ``"common"`` when null).
    """
    row = _assessment_doc(assessment_id)
    if not row:
        return None
    return row.get("owner_client_id")


def client_may_access_assessment(assessment_id: str, client_id: str | None) -> bool:
    """
    Decide whether a client session may open or submit an assessment.

    Rules:
      - Shared assessments (``owner_client_id`` is ``None``) → always allowed.
      - Client-scoped assessments → ``client_id`` must match the owner exactly.
      - Empty ``client_id`` on a scoped assessment → denied.

    Called from ``app.py`` on every client-facing assessment/submit/notebook route
    before loading questions or accepting answers.
    """
    owner = get_client_for_assessment(assessment_id)
    if owner is None:
        return True
    cid = (client_id or "").strip()
    if not cid:
        return False
    return owner == cid


def save_assessment_rows(
    assessment_id: str,
    rows: list[dict[str, Any]],
    client_id: str,
    *,
    language_code: str | None = None,
    language_label: str | None = None,
    topic_names: list[str] | None = None,
) -> None:
    """
    Persist questions for a **client-scoped** assessment (owner is set).

    Replaces all ``assessment_questions`` for ``assessment_id`` (delete + insert).
    Forces ``routing_flag="pyodide"`` because client-generated assessments are
    always in-browser. Prefer ``save_shared_assessment_rows`` for admin-created
    shared assessments with timing, certificates, and Jupyter routing.
    """
    safe = sanitize_client_id(client_id)
    lang = _normalize_language_code(language_code)
    lbl = _normalize_language_label(language_label)
    topics = _normalize_topic_names(topic_names)
    aid = assessment_id.strip()
    routing_flag = "pyodide"

    existing = _assessment_doc(aid)
    update: dict[str, Any] = {
        "owner_client_id": safe,
        "routing_flag": routing_flag,
    }
    if language_code is not None:
        update["language_code"] = lang
    if language_label is not None:
        update["language_label"] = lbl
    if topic_names is not None:
        update["topic_names"] = topics

    if existing:
        coll("assessments").update_one({"assessment_id": aid}, {"$set": update})
    else:
        coll("assessments").insert_one(
            {
                "assessment_id": aid,
                "owner_client_id": safe,
                "language_code": lang if language_code is not None else None,
                "language_label": lbl,
                "topic_names": topics,
                "routing_flag": routing_flag,
                "created_at": _utc_now_iso(),
                "is_timed": False,
                "duration_minutes": None,
                "notebook_grace_minutes": None,
                "allow_pyodide_paste": False,
                "certificate_enabled": False,
                "certificate_level": None,
            }
        )

    coll("assessment_questions").delete_many({"assessment_id": aid})
    if rows:
        coll("assessment_questions").insert_many(
            [_question_doc(row, aid) for row in rows]
        )


def update_assessment_question(
    assessment_id: str,
    question_id: str,
    *,
    question: str | None = None,
    code_snippet: str | None = None,
    options: str | None = None,
    correct_answer: str | None = None,
) -> bool:
    """
    Partially update one question row on an existing assessment.

    Only fields passed as non-``None`` are changed. Returns ``False`` if the
    question was not found or no fields were provided.

    Used by the admin PATCH endpoint (``routers/admin.py``) when an reviewer
    edits question text, options, or code snippet before publish.
    """
    update: dict[str, Any] = {}
    if question is not None:
        update["question"] = question.strip()
    if code_snippet is not None:
        update["code_snippet"] = code_snippet.strip() or None
    if options is not None:
        update["options"] = options
    if correct_answer is not None:
        update["correct_answer"] = correct_answer.strip()
    if not update:
        return False
    result = coll("assessment_questions").update_one(
        {
            "assessment_id": assessment_id.strip(),
            "question_id": str(question_id),
        },
        {"$set": update},
    )
    return result.matched_count > 0


def get_topics_by_names(topic_names: list[str]) -> list[Document]:
    """
    Load catalog ``topics`` documents matching the given display names.

    Returns ``Document`` wrappers (attribute access: ``.name``,
    ``.related_documents``, ``.modality``, etc.).

    Called by ``assessment_service._build_per_topic_strings`` when assembling
    LLM prompts — reference doc URLs from the catalog are appended per topic.
    """
    names = [n.strip() for n in topic_names if n and str(n).strip()]
    if not names:
        return []
    rows = coll("topics").find({"name": {"$in": names}})
    return [Document(r) for r in rows]


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
    allow_pyodide_paste: bool = False,
    certificate_enabled: bool = False,
    certificate_level: str | None = None,
) -> None:
    """
    Persist a **shared** assessment (``owner_client_id=None``) and its questions.

    This is the main write path after admin confirm/generate and improvement
    assessments. Replaces all question rows atomically (delete + insert).

    ``routing_flag`` must already be computed by the caller
    (``assessment_service._compute_routing_flag``) — this function only stores it.
    Timed and certificate fields are stored on the assessment document for
    ``get_assessment_metadata`` and client UI.
    """
    aid = assessment_id.strip()
    lang = _normalize_language_code(language_code)
    lbl = _normalize_language_label(language_label)
    topics = _normalize_topic_names(
        topic_names if topic_names is not None else []
    )
    cert_level = (
        (certificate_level or "").strip().lower() or None
        if certificate_enabled
        else None
    )

    existing = _assessment_doc(aid)
    doc: dict[str, Any] = {
        "assessment_id": aid,
        "owner_client_id": None,
        "routing_flag": routing_flag,
        "is_timed": is_timed,
        "duration_minutes": duration_minutes if is_timed else None,
        "notebook_grace_minutes": notebook_grace_minutes if is_timed else None,
        "allow_pyodide_paste": allow_pyodide_paste,
        "certificate_enabled": certificate_enabled,
        "certificate_level": cert_level,
    }
    if language_code is not None:
        doc["language_code"] = lang
    if language_label is not None:
        doc["language_label"] = lbl
    if topic_names is not None:
        doc["topic_names"] = topics

    if existing:
        coll("assessments").update_one({"assessment_id": aid}, {"$set": doc})
    else:
        doc.update(
            {
                "language_code": lang if language_code is not None else None,
                "language_label": lbl,
                "topic_names": topics,
                "created_at": _utc_now_iso(),
            }
        )
        coll("assessments").insert_one(doc)

    coll("assessment_questions").delete_many({"assessment_id": aid})
    if rows:
        coll("assessment_questions").insert_many(
            [_question_doc(row, aid) for row in rows]
        )


def read_questions_by_assessment(assessment_id: str) -> list[dict[str, Any]]:
    """
    Return all question rows for an assessment, ordered by stable integer ``id``.

    Shape matches what ``assessment_service`` and ``report_service`` expect
    (plain dicts with string keys). Empty list if the assessment id is unknown
    or has no questions yet.

    Heavily used: load assessment for client UI, submit grading, and reports.
    """
    aid = assessment_id.strip()
    rows = list(
        coll("assessment_questions")
        .find({"assessment_id": aid})
        .sort("id", 1)
    )
    return [
        {
            "assessment_id": aid,
            "question_id": r["question_id"],
            "question": r["question"],
            "type": r["type"],
            "options": r.get("options") or "",
            "correct_answer": r.get("correct_answer") or "",
            "topic_name": r.get("topic_name") or "",
            "code_snippet": r.get("code_snippet") or "",
            "bank_question_id": r.get("bank_question_id"),
            "difficulty": r.get("difficulty") or "",
            "sample_test_cases": r.get("sample_test_cases"),
            "coding_hint": r.get("coding_hint") or "",
        }
        for r in rows
    ]


def get_assessment_language_code(assessment_id: str) -> str | None:
    """
    Return normalized catalog language ``code`` stored on the assessment.

    Thin convenience wrapper around the assessments document; prefer
    ``get_assessment_metadata`` when you need multiple fields in one call.
    """
    row = _assessment_doc(assessment_id)
    if not row:
        return None
    return _normalize_language_code(row.get("language_code"))


def get_assessment_routing_flag(assessment_id: str) -> str:
    """
    Return ``routing_flag`` for an assessment (``pyodide`` or ``jupyter``).

    Defaults to ``"pyodide"`` if the assessment is missing or the field is empty.
    Used when deciding notebook vs in-browser flows without loading full metadata.
    """
    row = _assessment_doc(assessment_id)
    if not row:
        return "pyodide"
    return row.get("routing_flag") or "pyodide"


def get_topic_modality_by_names(topic_names: list[str]) -> dict[str, str]:
    """
    Map catalog topic name → modality (``pyodide`` or ``jupyter``).

    Called by ``assessment_service``, ``report_service``, and
    ``notebook_plan_service`` to know which questions need a notebook upload
    vs in-browser coding. Topics not in the catalog are omitted from the dict.
    """
    names = [n.strip() for n in topic_names if n and str(n).strip()]
    if not names:
        return {}
    rows = coll("topics").find({"name": {"$in": names}}, {"name": 1, "modality": 1})
    return {r["name"]: (r.get("modality") or "pyodide") for r in rows}


def get_topic_coding_editor_by_names(names: list[str]) -> dict[str, str | None]:
    """
    Map catalog topic name → coding editor language for shell topics.

    Returns ``"shell"``, ``"powershell"``, or ``None`` per topic. Only topics
    explicitly configured in the catalog appear in the result.

    Used by ``assessment_service`` when building the client assessment payload
    so the UI picks the correct editor (e.g. bash vs PowerShell).
    """
    cleaned = [n.strip() for n in names if n and str(n).strip()]
    if not cleaned:
        return {}
    rows = coll("topics").find(
        {"name": {"$in": cleaned}},
        {"name": 1, "coding_editor_language": 1},
    )
    out: dict[str, str | None] = {}
    for r in rows:
        cel = (r.get("coding_editor_language") or "").strip().lower() or None
        if cel in ("shell", "powershell"):
            out[r["name"]] = cel
        else:
            out[r["name"]] = None
    return out


def get_assessment_metadata(assessment_id: str) -> dict[str, Any]:
    """
    Single-call summary of assessment settings for API and service layers.

    Returns language, routing, topic list, Jupyter subset, timed-assessment
    config, paste allowance, and certificate flags. If the assessment does not
    exist, returns a safe default dict (empty topics, ``is_timed=False``, etc.)
    so callers can branch without extra existence checks.

    Primary consumers: ``assessment_service`` (load/submit), ``report_service``,
    ``certificate_service``, ``employee_profile_service._load_assessment_records``.
    """
    row = _assessment_doc(assessment_id)
    if not row:
        return {
            "language_code": None,
            "routing_flag": "pyodide",
            "topic_names": [],
            "jupyter_topic_names": [],
            "is_timed": False,
            "duration_minutes": None,
            "notebook_grace_minutes": None,
            "allow_pyodide_paste": False,
            "certificate_enabled": False,
            "certificate_level": None,
            "language_label": None,
        }
    topic_names = _coerce_stored_topic_names(row.get("topic_names"))
    jupyter_topic_names: list[str] = []
    if topic_names:
        jupyter_topic_names = [
            r["name"]
            for r in coll("topics").find(
                {"name": {"$in": topic_names}, "modality": "jupyter"},
                {"name": 1},
            )
        ]
    return {
        "language_code": _normalize_language_code(row.get("language_code")),
        "routing_flag": row.get("routing_flag") or "pyodide",
        "topic_names": topic_names,
        "jupyter_topic_names": jupyter_topic_names,
        "is_timed": bool(row.get("is_timed")),
        "duration_minutes": row.get("duration_minutes"),
        "notebook_grace_minutes": row.get("notebook_grace_minutes"),
        "allow_pyodide_paste": bool(row.get("allow_pyodide_paste")),
        "certificate_enabled": bool(row.get("certificate_enabled")),
        "certificate_level": (row.get("certificate_level") or "").strip() or None,
        "language_label": (row.get("language_label") or "").strip() or None,
    }


def list_assessments_summary() -> list[dict[str, Any]]:
    """
    Admin dashboard list: every assessment with counts and display labels.

    Joins in memory: assessment docs, per-assessment question counts (aggregation),
    and catalog language names for friendly ``language_name``. Sorted newest
    ``created_at`` first.

    Exposed as ``GET /admin/assessments`` via ``routers/admin.py``.
    """
    assessments = list(coll("assessments").find())
    langs = list(coll("languages").find())

    lang_name_by_code_cf: dict[str, str] = {}
    for lg in langs:
        k = _normalize_language_code(lg.get("code"))
        if k:
            lang_name_by_code_cf[k.casefold()] = (
                (lg.get("name") or "").strip()[:_MAX_LANGUAGE_LABEL] or k
            )

    count_by_id: dict[str, int] = {}
    for doc in coll("assessment_questions").aggregate(
        [{"$group": {"_id": "$assessment_id", "n": {"$sum": 1}}}]
    ):
        count_by_id[str(doc["_id"])] = int(doc["n"])

    result: list[dict[str, Any]] = []
    for a in assessments:
        aid = a["assessment_id"]
        cid = a.get("owner_client_id") or "common"
        source = "shared" if a.get("owner_client_id") is None else "client"
        lc = _normalize_language_code(a.get("language_code"))
        stored_label = (a.get("language_label") or "").strip() or None
        catalog_name = lang_name_by_code_cf.get(lc.casefold()) if lc else None
        language_name = catalog_name or stored_label or (lc if lc else None)
        topics = _coerce_stored_topic_names(a.get("topic_names"))
        result.append(
            {
                "assessment_id": aid,
                "client_id": cid,
                "question_count": count_by_id.get(aid, 0),
                "source": source,
                "language_code": lc,
                "language_label": stored_label,
                "language_name": language_name,
                "topic_names": topics,
                "created_at": (a.get("created_at") or "").strip() or None,
                "routing_flag": a.get("routing_flag"),
                "is_timed": bool(a.get("is_timed")),
                "duration_minutes": a.get("duration_minutes"),
                "notebook_grace_minutes": a.get("notebook_grace_minutes"),
            }
        )
    return sorted(
        result,
        key=lambda x: (_created_at_sort_key(x), x["assessment_id"]),
        reverse=True,
    )


def delete_assessment(assessment_id: str) -> None:
    """
    Remove an assessment and all dependent rows for that id.

    Cascade (manual): submissions → assessment_attempts → assessment_questions
    → assessments document. Does **not** delete question-bank or mastery rows.

    Raises ``ValueError`` if id is empty or assessment not found. Used by admin
    ``DELETE /admin/assessments/{assessment_id}``.
    """
    aid = assessment_id.strip()
    if not aid:
        raise ValueError("Assessment ID is required")
    if not _assessment_doc(aid):
        raise ValueError("Assessment not found")
    coll("submissions").delete_many({"assessment_id": aid})
    coll("assessment_attempts").delete_many({"assessment_id": aid})
    coll("assessment_questions").delete_many({"assessment_id": aid})
    coll("assessments").delete_one({"assessment_id": aid})


def get_participant_in_browser_submissions(
    assessment_id: str,
    employee_id: str,
) -> list[dict[str, Any]]:
    """
    In-browser submission rows for one participant on one assessment.

    Excludes Jupyter notebook rows (``question_id="notebook"`` or
    ``routing_flag="jupyter"``). Matches employee by the id prefix in
    ``user_id`` (``"E1001 | Name"``), case-insensitive — the display name is
    ignored for matching.

    Called by ``report_service.build_report`` to assemble per-question scores
    without re-grading.
    """
    from services.attempt_service import normalize_employee_id

    eid_norm = normalize_employee_id(employee_id)
    if not eid_norm:
        return []

    aid = assessment_id.strip()
    rows = list(
        coll("submissions")
        .find(
            {
                "assessment_id": aid,
                "question_id": {"$ne": _NOTEBOOK_QUESTION_ID},
                "routing_flag": {"$ne": "jupyter"},
            }
        )
        .sort("id", 1)
    )

    out: list[dict[str, Any]] = []
    for r in rows:
        uid = r.get("user_id") or ""
        part = uid.split("|", 1)[0].strip().casefold()
        if part != eid_norm:
            continue
        out.append(
            {
                "assessment_id": r["assessment_id"],
                "user_id": r["user_id"],
                "question_id": r["question_id"],
                "user_answer": r.get("user_answer"),
                "score": r.get("score"),
                "feedback": r.get("feedback"),
                "timestamp": r.get("timestamp"),
                "routing_flag": r.get("routing_flag"),
            }
        )
    return out


def list_employee_completed_assessments(employee_id: str) -> list[dict[str, Any]]:
    """
    Distinct assessments this employee has submitted (in-browser only), newest first.

    Scans all non-notebook submissions and groups by ``assessment_id``, tracking
    latest and earliest timestamp per assessment. Used as the index step in
    ``employee_profile_service._load_assessment_records`` before loading full
    reports per assessment.
    """
    from services.attempt_service import normalize_employee_id

    eid = normalize_employee_id(employee_id)
    if not eid:
        return []

    rows = list(
        coll("submissions").find(
            {
                "question_id": {"$ne": _NOTEBOOK_QUESTION_ID},
                "routing_flag": {"$ne": "jupyter"},
            }
        )
    )

    by_aid: dict[str, dict[str, Any]] = {}
    for r in rows:
        uid = r.get("user_id") or ""
        part = uid.split("|", 1)[0].strip().casefold()
        if part != eid:
            continue
        aid = r["assessment_id"]
        ts = r.get("timestamp") or ""
        if aid not in by_aid:
            by_aid[aid] = {
                "assessment_id": aid,
                "user_id": r["user_id"],
                "submitted_at": ts,
                "earliest_timestamp": ts,
            }
        else:
            if ts > by_aid[aid]["submitted_at"]:
                by_aid[aid]["submitted_at"] = ts
            if ts < by_aid[aid]["earliest_timestamp"]:
                by_aid[aid]["earliest_timestamp"] = ts

    out = list(by_aid.values())
    out.sort(key=lambda x: str(x.get("submitted_at") or ""), reverse=True)
    return out


def count_employee_mastered_by_topic(employee_id: str) -> dict[str, int]:
    """
    Count mastered bank questions grouped by ``question_bank.topic_name``.

    Reads ``employee_question_mastery`` joined to ``question_bank`` — does not
    recompute from submissions. Empty topic names bucket as ``"General"``.

    Used by ``employee_profile_service.get_employee_report`` for the mastery
    section of the skills report UI.
    """
    from services.attempt_service import normalize_employee_id

    eid = normalize_employee_id(employee_id)
    if not eid:
        return {}

    mastered_ids = [
        r["bank_question_id"]
        for r in coll("employee_question_mastery").find(
            {"employee_id": eid},
            {"bank_question_id": 1},
        )
    ]
    if not mastered_ids:
        return {}

    out: dict[str, int] = {}
    for bq in coll("question_bank").find(
        {"id": {"$in": mastered_ids}},
        {"topic_name": 1},
    ):
        key = (bq.get("topic_name") or "").strip() or "General"
        out[key] = out.get(key, 0) + 1
    return out


def count_employee_needs_practice_bank_questions(employee_id: str) -> int:
    """
    Count bank questions the employee should revisit (wrong ≥2 times, not mastered).

    Walks in-browser submissions, maps questions to ``bank_question_id`` via
    ``assessment_questions``, and counts distinct bank ids with score < 70 on
    at least two attempts while not present in ``employee_question_mastery``.

    Paired with ``count_employee_mastered_by_topic`` on the employee report.
    """
    from collections import defaultdict

    from services.attempt_service import normalize_employee_id
    from services.question_bank_service import get_employee_mastered_bank_ids

    eid = normalize_employee_id(employee_id)
    if not eid:
        return 0

    mastered = get_employee_mastered_bank_ids(employee_id)
    wrong_counts: dict[int, int] = defaultdict(int)

    subs = list(
        coll("submissions").find(
            {
                "question_id": {"$ne": _NOTEBOOK_QUESTION_ID},
                "routing_flag": {"$ne": "jupyter"},
            }
        )
    )
    if not subs:
        return 0

    aids = {
        s["assessment_id"]
        for s in subs
        if _submission_row_belongs_to_employee(s.get("user_id") or "", eid)
    }
    if not aids:
        return 0

    bank_by_key: dict[tuple[str, str], int] = {}
    for q in coll("assessment_questions").find(
        {
            "assessment_id": {"$in": list(aids)},
            "bank_question_id": {"$ne": None},
        },
        {"assessment_id": 1, "question_id": 1, "bank_question_id": 1},
    ):
        bank_by_key[(q["assessment_id"], str(q["question_id"]))] = int(
            q["bank_question_id"]
        )

    for s in subs:
        if not _submission_row_belongs_to_employee(s.get("user_id") or "", eid):
            continue
        bid = bank_by_key.get((s["assessment_id"], str(s["question_id"])))
        if bid is None:
            continue
        try:
            score = float(s.get("score") or 0)
        except (TypeError, ValueError):
            score = 0.0
        if score < 70:
            wrong_counts[bid] += 1

    return sum(1 for bid, n in wrong_counts.items() if bid not in mastered and n >= 2)


def _submission_row_belongs_to_employee(user_id: str, eid_norm: str) -> bool:
    """
    True when ``user_id`` label belongs to normalized employee id.

    Compares only the part before ``|`` in ``user_id``, case-insensitive.
    Shared by submission listing helpers in this module.
    """
    part = (user_id or "").split("|", 1)[0].strip().casefold()
    return part == eid_norm


def list_all_submissions() -> list[dict[str, Any]]:
    """
    All submission rows for the admin submissions table, newest timestamp first.

    Adds ``client_id`` (or ``"common"`` when ``submitter_client_id`` is null).
    Exposed as ``GET /admin/submissions``.
    """
    rows = list(coll("submissions").find().sort("timestamp", -1))
    out: list[dict[str, Any]] = []
    for r in rows:
        cid = r.get("submitter_client_id") if r.get("submitter_client_id") else "common"
        out.append(
            {
                "assessment_id": r["assessment_id"],
                "user_id": r["user_id"],
                "question_id": r["question_id"],
                "user_answer": r.get("user_answer"),
                "score": r.get("score"),
                "feedback": r.get("feedback"),
                "timestamp": r.get("timestamp"),
                "client_id": cid,
                "routing_flag": r.get("routing_flag"),
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
    """
    Insert one graded answer (or notebook payload) into ``submissions``.

    Appends a row — does not upsert. ``user_id`` is typically ``"employeeId | name"``.
    ``routing_flag`` distinguishes pyodide vs jupyter paths; notebook uploads use
    ``question_id="notebook"`` and optional ``raw_notebook`` JSON.

    Called from ``assessment_service.submit_assessment`` (per question) and
    ``notebook_service`` (single notebook row after Jupyter grading).
    """
    coll("submissions").insert_one(
        {
            "id": next_id("submissions"),
            "assessment_id": assessment_id,
            "user_id": user_id,
            "question_id": question_id,
            "user_answer": user_answer,
            "score": score,
            "feedback": feedback,
            "timestamp": timestamp,
            "submitter_client_id": submitter_client_id,
            "routing_flag": routing_flag,
            "raw_notebook": raw_notebook,
        }
    )
