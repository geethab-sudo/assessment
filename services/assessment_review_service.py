"""Admin assessment review, re-review, incremental save, and single-question regenerate."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from services import db_service, question_bank_service
from services.assessment_service import (
    LEVEL_TO_DIFFICULTY,
    _compute_routing_flag,
    _gen_kwargs,
    _options_for_csv,
    _parse_options,
)
from services.database import coll, next_id
from services.ids import generate_assessment_id
from services.llm_service import generate_questions


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _content_fingerprint(q: dict[str, Any]) -> str:
    opts = q.get("options")
    if isinstance(opts, list):
        opts_key = json.dumps(opts, ensure_ascii=False, sort_keys=True)
    else:
        opts_key = str(opts or "")
    cases = q.get("sample_test_cases") or []
    cases_key = json.dumps(cases, ensure_ascii=False, sort_keys=True)
    parts = [
        str(q.get("type") or "").strip().lower(),
        str(q.get("topic_name") or "").strip(),
        str(q.get("question") or "").strip(),
        str(q.get("code_snippet") or "").strip(),
        opts_key,
        str(q.get("correct_answer") or "").strip(),
        cases_key,
        str(q.get("coding_hint") or "").strip(),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _review_item_from_row(row: dict[str, Any]) -> dict[str, Any]:
    raw_opts = row.get("options") or ""
    options = _parse_options(raw_opts) if raw_opts else []
    item: dict[str, Any] = {
        "question_id": str(row["question_id"]),
        "type": row["type"],
        "question": row["question"],
        "code_snippet": row.get("code_snippet") or "",
        "options": options,
        "correct_answer": row.get("correct_answer") or "",
        "topic_name": row.get("topic_name") or "",
        "saved_at": row.get("saved_at"),
        "is_dirty": False,
    }
    if row.get("bank_question_id") is not None:
        item["bank_question_id"] = int(row["bank_question_id"])
    if row.get("sample_test_cases"):
        item["sample_test_cases"] = row["sample_test_cases"]
    hint = row.get("coding_hint")
    if hint:
        item["coding_hint"] = hint
    return item


def _default_topic_label(doc: dict[str, Any]) -> str:
    explicit = (doc.get("topic") or "").strip()
    if explicit:
        return explicit
    names = [str(n).strip() for n in (doc.get("topic_names") or []) if n and str(n).strip()]
    if names:
        return ", ".join(names)
    return "Assessment"


def _metadata_from_assessment_doc(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "topic": _default_topic_label(doc),
        "level": (doc.get("level") or "beginner").strip().lower(),
        "language_code": doc.get("language_code"),
        "language_label": doc.get("language_label"),
        "topic_names": doc.get("topic_names") or [],
        "per_topic_config": doc.get("per_topic_config") or {},
        "is_timed": bool(doc.get("is_timed")),
        "duration_minutes": doc.get("duration_minutes"),
        "notebook_grace_minutes": doc.get("notebook_grace_minutes"),
        "allow_pyodide_paste": bool(doc.get("allow_pyodide_paste")),
        "certificate_enabled": bool(doc.get("certificate_enabled")),
        "question_source": doc.get("question_source") or "generate_new",
        "include_sample_test_cases": bool(doc.get("include_sample_test_cases")),
        "include_beginner_coding_hints": bool(doc.get("include_beginner_coding_hints")),
        "generation_provider": doc.get("generation_provider") or "grok",
        "alias": (doc.get("alias") or "").strip() or None,
    }


def _row_from_review_item(q: dict[str, Any], *, level: str) -> dict[str, Any]:
    from services.llm_service import _normalize_sample_test_cases

    row: dict[str, Any] = {
        "question_id": str(q["question_id"]),
        "question": (q.get("question") or "").strip(),
        "type": (q.get("type") or "").strip().lower(),
        "options": _options_for_csv(q.get("options") or []),
        "correct_answer": (q.get("correct_answer") or "").strip(),
        "topic_name": (q.get("topic_name") or "").strip(),
        "code_snippet": (q.get("code_snippet") or "").strip(),
        "difficulty": level.strip().lower(),
    }
    bid = q.get("bank_question_id")
    if bid is not None:
        row["bank_question_id"] = int(bid)
    if q.get("sample_test_cases"):
        cases = _normalize_sample_test_cases(q["sample_test_cases"])
        if cases:
            row["sample_test_cases"] = cases
    hint = q.get("coding_hint")
    if hint:
        row["coding_hint"] = str(hint).strip()
    return row


def _next_question_id(assessment_id: str) -> str:
    rows = coll("assessment_questions").find(
        {"assessment_id": assessment_id.strip()},
        {"question_id": 1},
    )
    nums: list[int] = []
    for r in rows:
        try:
            nums.append(int(str(r.get("question_id"))))
        except ValueError:
            continue
    return str(max(nums, default=0) + 1)


def _has_submissions(assessment_id: str, question_id: str) -> bool:
    return (
        coll("submissions").find_one(
            {
                "assessment_id": assessment_id.strip(),
                "question_id": str(question_id),
            },
            {"_id": 1},
        )
        is not None
    )


def get_review_status(assessment_id: str) -> str:
    doc = coll("assessments").find_one({"assessment_id": assessment_id.strip()})
    if not doc:
        raise ValueError("Assessment not found")
    return (doc.get("review_status") or "published").strip() or "published"


def assert_participant_may_load(assessment_id: str) -> None:
    status = get_review_status(assessment_id)
    if status != "published":
        raise ValueError(
            "This assessment is not published yet. Ask your administrator to finish review."
        )


def load_review_bundle(assessment_id: str) -> dict[str, Any]:
    aid = assessment_id.strip()
    doc = coll("assessments").find_one({"assessment_id": aid})
    if not doc:
        raise ValueError("Assessment not found")
    rows = db_service.read_questions_by_assessment(aid)
    questions = [_review_item_from_row(r) for r in rows]
    saved_count = sum(1 for q in questions if q.get("saved_at"))
    meta = _metadata_from_assessment_doc(doc)
    return {
        "assessment_id": aid,
        "review_status": (doc.get("review_status") or "published").strip() or "published",
        **meta,
        "questions": questions,
        "saved_count": saved_count,
        "question_count": len(questions),
    }


def _insert_pending_review_questions(
    assessment_id: str,
    questions: list[dict[str, Any]],
    *,
    level: str,
) -> list[dict[str, Any]]:
    """Persist preview questions on draft creation (no saved_at until admin confirms each)."""
    seeded: list[dict[str, Any]] = []
    for i, q in enumerate(questions):
        qid = str(q.get("question_id") or (i + 1)).strip()
        row = _row_from_review_item({**q, "question_id": qid}, level=level)
        row.pop("bank_question_id", None)
        coll("assessment_questions").insert_one(
            {
                "id": next_id("assessment_questions"),
                "assessment_id": assessment_id,
                **row,
            }
        )
        seeded.append(_review_item_from_row(row))
    return seeded


def create_review_draft(
    metadata: dict[str, Any],
    *,
    questions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    aid = generate_assessment_id()
    level = metadata["level"].strip().lower()
    if level not in LEVEL_TO_DIFFICULTY:
        raise ValueError("level must be beginner, intermediate, or advanced")

    topic_names = [
        n.strip() for n in (metadata.get("topic_names") or []) if n and str(n).strip()
    ]
    routing_flag = _compute_routing_flag(topic_names)
    cert_level = level if metadata.get("certificate_enabled") else None

    from services import attempt_service

    dur, grace = attempt_service.validate_timed_config(
        bool(metadata.get("is_timed")),
        metadata.get("duration_minutes"),
        metadata.get("notebook_grace_minutes"),
    )

    now = _utc_now_iso()
    doc: dict[str, Any] = {
        "assessment_id": aid,
        "owner_client_id": None,
        "routing_flag": routing_flag,
        "review_status": "draft",
        "topic": (metadata.get("topic") or "").strip(),
        "level": level,
        "language_code": (metadata.get("language_code") or "").strip()[:32] or None,
        "language_label": (metadata.get("language_label") or "").strip()[:256] or None,
        "topic_names": topic_names,
        "per_topic_config": metadata.get("per_topic_config") or {},
        "is_timed": bool(metadata.get("is_timed")),
        "duration_minutes": dur,
        "notebook_grace_minutes": grace,
        "allow_pyodide_paste": bool(metadata.get("allow_pyodide_paste")),
        "certificate_enabled": bool(metadata.get("certificate_enabled")),
        "certificate_level": cert_level,
        "question_source": metadata.get("question_source") or "generate_new",
        "include_sample_test_cases": bool(metadata.get("include_sample_test_cases")),
        "include_beginner_coding_hints": bool(metadata.get("include_beginner_coding_hints")),
        "generation_provider": (metadata.get("generation_provider") or "grok").strip().lower(),
        "alias": (metadata.get("alias") or "").strip()[:120] or None,
        "created_at": now,
        "updated_at": now,
    }
    coll("assessments").insert_one(doc)

    seeded = _insert_pending_review_questions(aid, questions or [], level=level)
    return {
        "assessment_id": aid,
        "review_status": "draft",
        "questions": seeded,
        "question_count": len(seeded),
    }


def update_assessment_alias(assessment_id: str, alias: str | None) -> dict[str, Any]:
    aid = assessment_id.strip()
    if not coll("assessments").find_one({"assessment_id": aid}, {"_id": 1}):
        raise ValueError("Assessment not found")
    normalized = (alias or "").strip()[:120] or None
    coll("assessments").update_one(
        {"assessment_id": aid},
        {"$set": {"alias": normalized, "updated_at": _utc_now_iso()}},
    )
    return {"assessment_id": aid, "alias": normalized}


def save_review_question(
    assessment_id: str,
    question_id: str,
    question: dict[str, Any],
) -> dict[str, Any]:
    aid = assessment_id.strip()
    qid = str(question_id).strip()
    doc = coll("assessments").find_one({"assessment_id": aid})
    if not doc:
        raise ValueError("Assessment not found")

    level = (doc.get("level") or "beginner").strip().lower()
    language_code = doc.get("language_code")
    new_row = _row_from_review_item({**question, "question_id": qid}, level=level)
    new_fp = _content_fingerprint(new_row)

    existing = coll("assessment_questions").find_one(
        {"assessment_id": aid, "question_id": qid}
    )
    revised = False
    target_qid = qid

    if existing:
        old_fp = _content_fingerprint(
            {
                "type": existing.get("type"),
                "topic_name": existing.get("topic_name"),
                "question": existing.get("question"),
                "code_snippet": existing.get("code_snippet"),
                "options": existing.get("options"),
                "correct_answer": existing.get("correct_answer"),
                "sample_test_cases": existing.get("sample_test_cases"),
                "coding_hint": existing.get("coding_hint"),
            }
        )
        if new_fp != old_fp:
            revised = True
            if _has_submissions(aid, qid):
                target_qid = _next_question_id(aid)
                new_row["question_id"] = target_qid
            new_row.pop("bank_question_id", None)

    now = _utc_now_iso()
    new_row["saved_at"] = now

    bank_id = new_row.get("bank_question_id")
    if bank_id is None or revised:
        hash_to_id = question_bank_service.add_questions_to_bank(
            [new_row], level, language_code
        )
        if hash_to_id:
            new_row["bank_question_id"] = next(iter(hash_to_id.values()))
        question_bank_service.link_assessment_questions_to_bank(
            aid, hash_to_id, level
        )
    elif bank_id is not None:
        question_bank_service.increment_question_usage(int(bank_id))

    if existing and revised and target_qid != qid:
        if _has_submissions(aid, qid):
            coll("assessment_questions").update_one(
                {"assessment_id": aid, "question_id": qid},
                {"$set": {"superseded_by": target_qid}},
            )
        else:
            coll("assessment_questions").delete_one(
                {"assessment_id": aid, "question_id": qid}
            )
        coll("assessment_questions").insert_one(
            {
                "id": next_id("assessment_questions"),
                "assessment_id": aid,
                **new_row,
            }
        )
    elif existing:
        coll("assessment_questions").update_one(
            {"assessment_id": aid, "question_id": target_qid},
            {"$set": new_row},
        )
    else:
        coll("assessment_questions").insert_one(
            {
                "id": next_id("assessment_questions"),
                "assessment_id": aid,
                **new_row,
            }
        )

    review_status = doc.get("review_status") or "draft"
    if review_status == "published":
        review_status = "in_review"
    coll("assessments").update_one(
        {"assessment_id": aid},
        {
            "$set": {
                "review_status": review_status,
                "updated_at": now,
                "routing_flag": _compute_routing_flag(doc.get("topic_names") or []),
            }
        },
    )

    return {
        "ok": True,
        "assessment_id": aid,
        "question_id": target_qid,
        "bank_question_id": new_row.get("bank_question_id"),
        "saved_at": now,
        "revised": revised,
    }


def delete_review_question(assessment_id: str, question_id: str) -> None:
    aid = assessment_id.strip()
    qid = str(question_id).strip()
    if _has_submissions(aid, qid):
        raise ValueError(
            "Cannot remove this question: participants have already submitted answers for it."
        )
    result = coll("assessment_questions").delete_one(
        {"assessment_id": aid, "question_id": qid}
    )
    if result.deleted_count == 0:
        raise ValueError("Question not found")
    remaining = coll("assessment_questions").count_documents(
        {"assessment_id": aid, "superseded_by": {"$exists": False}}
    )
    if remaining == 0:
        raise ValueError("Cannot remove the last question from an assessment.")
    coll("assessments").update_one(
        {"assessment_id": aid},
        {"$set": {"updated_at": _utc_now_iso()}},
    )


def publish_review(
    assessment_id: str,
    questions: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    aid = assessment_id.strip()
    doc = coll("assessments").find_one({"assessment_id": aid})
    if not doc:
        raise ValueError("Assessment not found")

    if not questions:
        raise ValueError("At least one question is required.")

    for q in questions:
        qid = str(q.get("question_id") or "").strip()
        if not qid:
            raise ValueError("Each question must have a question_id")
        save_review_question(aid, qid, q)

    meta = metadata or _metadata_from_assessment_doc(doc)
    level = meta.get("level") or doc.get("level") or "beginner"
    topic_names = meta.get("topic_names") or doc.get("topic_names") or []
    routing_flag = _compute_routing_flag(topic_names)

    from services import attempt_service

    dur, grace = attempt_service.validate_timed_config(
        bool(meta.get("is_timed", doc.get("is_timed"))),
        meta.get("duration_minutes", doc.get("duration_minutes")),
        meta.get("notebook_grace_minutes", doc.get("notebook_grace_minutes")),
    )

    cert_enabled = bool(meta.get("certificate_enabled", doc.get("certificate_enabled")))
    cert_level = (level if cert_enabled else None)

    update_fields: dict[str, Any] = {
        "review_status": "published",
        "routing_flag": routing_flag,
        "topic": (meta.get("topic") or doc.get("topic") or "").strip(),
        "level": str(level).strip().lower(),
        "is_timed": bool(meta.get("is_timed", doc.get("is_timed"))),
        "duration_minutes": dur,
        "notebook_grace_minutes": grace,
        "allow_pyodide_paste": bool(
            meta.get("allow_pyodide_paste", doc.get("allow_pyodide_paste"))
        ),
        "certificate_enabled": cert_enabled,
        "certificate_level": cert_level,
        "updated_at": _utc_now_iso(),
    }
    if meta.get("alias") is not None:
        update_fields["alias"] = (meta.get("alias") or "").strip()[:120] or None
    if meta.get("language_code") is not None:
        update_fields["language_code"] = (meta.get("language_code") or "").strip()[:32] or None
    if meta.get("language_label") is not None:
        update_fields["language_label"] = (meta.get("language_label") or "").strip()[:256] or None
    if meta.get("topic_names") is not None:
        update_fields["topic_names"] = meta.get("topic_names") or []

    coll("assessments").update_one({"assessment_id": aid}, {"$set": update_fields})

    count = coll("assessment_questions").count_documents(
        {"assessment_id": aid, "superseded_by": {"$exists": False}}
    )
    return {
        "assessment_id": aid,
        "review_status": "published",
        "question_count": count,
    }


def regenerate_review_question(body: dict[str, Any]) -> dict[str, Any]:
    level = body["level"].strip().lower()
    difficulty = LEVEL_TO_DIFFICULTY.get(level)
    if not difficulty:
        raise ValueError("level must be beginner, intermediate, or advanced")

    qtype = body["question_type"].strip().lower()
    topic_name = (body.get("topic_name") or "").strip()
    ref = body["reference_question"]
    preference = (body.get("admin_preference") or "").strip()
    topic_prompt = topic_name or "general programming"
    if preference:
        topic_prompt = f"{topic_prompt}. Admin preference: {preference}"

    gen_kwargs = _gen_kwargs(
        level,
        include_sample_test_cases=bool(body.get("include_sample_test_cases")),
        include_beginner_coding_hints=bool(body.get("include_beginner_coding_hints")),
        generation_provider=(body.get("generation_provider") or "grok").strip().lower(),
    )

    generated = generate_questions(
        topic_prompt,
        difficulty,
        [qtype],
        questions_per_type={qtype: 1},
        assessment_id=f"regen-{ref.get('question_id', '0')}",
        **gen_kwargs,
    )
    if not generated:
        raise RuntimeError("LLM did not return a replacement question.")

    from services.assessment_service import _row_from_question

    row = _row_from_question(generated[0], ref.get("question_id") or "1", topic_name)
    item: dict[str, Any] = {
        "question_id": str(ref.get("question_id") or "1"),
        "type": row["type"],
        "question": row["question"],
        "code_snippet": row.get("code_snippet") or "",
        "options": _parse_options(row.get("options") or "") if row.get("options") else [],
        "correct_answer": row.get("correct_answer") or "",
        "topic_name": topic_name,
        "saved_at": None,
        "is_dirty": True,
    }
    if row.get("sample_test_cases"):
        item["sample_test_cases"] = row["sample_test_cases"]
    if row.get("coding_hint"):
        item["coding_hint"] = row["coding_hint"]
    return item


def ensure_assessment_review_defaults() -> None:
    """Backfill review_status=published for legacy assessments."""
    coll("assessments").update_many(
        {"review_status": {"$exists": False}},
        {"$set": {"review_status": "published"}},
    )
