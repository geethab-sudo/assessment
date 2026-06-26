#!/usr/bin/env python3
"""
Seed demo participants and a shared Tier 1 Beginner Python assessment.

Safe to re-run: replaces the demo assessment questions and rewrites the three
students' submissions (same assessment id each time).

Questions are loaded from ``demo_questions_snapshot.json`` — real Tier 1 beginner
Python items captured from the question bank. Re-capture with ``--refresh-snapshot``
after the bank has better content (requires MONGODB_URI).

Prerequisites:
  - MONGODB_URI in .env
  - Catalog seeded: ``python scripts/seed_sample_catalog.py``
  - Question bank populated (admin-generated assessments or prior seed run)

Usage (from project root):
  python scripts/seed_demo_students.py
  python scripts/seed_demo_students.py --refresh-snapshot   # re-export from DB

---------------------------------------------------------------------------
DEMO ASSESSMENT ID (paste on /client → Assessment ID):
  ASM-DEMO0001
---------------------------------------------------------------------------

Demo students (employee ID | name):
  C001 | María   — strong (~91% overall; no weak topics)
  C002 | Kumar   — regular (~68%; mixed weak/ok topics)
  C003 | Oscar   — struggling (~42%; many weak topics)

All three completed the same assessment: Tier 1 Beginner Python (25 questions).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env", override=True)

from services import db_service, question_bank_service  # noqa: E402
from services.assessment_service import SCORE_CORRECT_THRESHOLD, _is_answer_correct  # noqa: E402
from services.attempt_service import normalize_employee_id  # noqa: E402
from services.database import coll, init_db  # noqa: E402

# ---------------------------------------------------------------------------
# Fixed demo identifiers (documented for QA / client UI)
# ---------------------------------------------------------------------------

MOCK_ASSESSMENT_ID = "ASM-DEMO0001"
MOCK_LANGUAGE_CODE = "py"
MOCK_LANGUAGE_LABEL = "Python"
MOCK_LEVEL = "beginner"

_SNAPSHOT_PATH = Path(__file__).resolve().parent / "demo_questions_snapshot.json"
_TIER1_PRESETS_PATH = ROOT / "frontend" / "src" / "data" / "tier1EvaluationPresets.json"

# Per-question scores (25 total) — order matches snapshot question order.
_SCORES_MARIA = [
    95, 92, 90, 93, 88,
    94, 91, 96, 92, 90,
    88, 90, 92, 85, 91,
    78, 82, 75,
    90, 88, 92,
    95, 93, 91, 94,
]

_SCORES_KUMAR = [
    70, 72, 68, 74, 71,
    65, 62, 70, 68, 64,
    78, 75, 72, 80, 76,
    55, 50, 58,
    60, 65, 62,
    70, 68, 72, 74,
]

_SCORES_OSCAR = [
    40, 45, 42, 48, 38,
    35, 40, 32, 38, 36,
    45, 42, 48, 40, 44,
    28, 32, 30,
    38, 35, 40,
    50, 45, 48, 52,
]

DEMO_STUDENTS: list[dict[str, Any]] = [
    {
        "employee_id": "C001",
        "name": "María",
        "submitted_at": "2026-05-01T14:30:00+00:00",
        "scores": _SCORES_MARIA,
        "profile_note": "strong (~91% overall; no weak topics)",
    },
    {
        "employee_id": "C002",
        "name": "Kumar",
        "submitted_at": "2026-05-02T11:15:00+00:00",
        "scores": _SCORES_KUMAR,
        "profile_note": "regular (~68%; some topics below 70%)",
    },
    {
        "employee_id": "C003",
        "name": "Oscar",
        "submitted_at": "2026-05-03T09:45:00+00:00",
        "scores": _SCORES_OSCAR,
        "profile_note": "struggling (~42%; most topics weak)",
    },
]


def _load_beginner_preset() -> dict[str, Any]:
    data = json.loads(_TIER1_PRESETS_PATH.read_text(encoding="utf-8"))
    for preset in data.get("presets") or []:
        if (preset.get("name") or "").strip().lower() == "beginner":
            return preset
    raise RuntimeError("Beginner preset not found in tier1EvaluationPresets.json")


def _bank_row_to_snapshot_item(qid: int, bq: dict[str, Any]) -> dict[str, Any]:
    return {
        "question_id": str(qid),
        "question": bq["question"],
        "type": bq["type"],
        "options": bq.get("options") or "",
        "correct_answer": bq.get("correct_answer") or "",
        "topic_name": bq.get("topic_name") or "",
        "code_snippet": bq.get("code_snippet") or "",
        "difficulty": MOCK_LEVEL,
        "source_bank_question_id": bq.get("bank_question_id"),
    }


def export_snapshot_from_bank() -> list[dict[str, Any]]:
    """Pull Tier 1 beginner questions from the live question bank."""
    preset = _load_beginner_preset()
    rows: list[dict[str, Any]] = []
    topic_names: list[str] = []
    qid = 1
    used_bank_ids: set[int] = set()

    for topic_cfg in preset.get("topics") or []:
        topic = (topic_cfg.get("topic_name") or "").strip()
        if not topic:
            continue
        topic_names.append(topic)
        for qtype in ("mcq", "coding"):
            needed = int(topic_cfg.get(qtype) or 0)
            if needed <= 0:
                continue
            found, shortage = question_bank_service.find_bank_questions(
                [topic],
                MOCK_LEVEL,
                needed,
                question_type=qtype,
                exclude_bank_ids=used_bank_ids,
            )
            if shortage:
                raise RuntimeError(
                    f"Question bank shortage for demo seed: {topic} / {qtype} "
                    f"(need {needed}, found {len(found)}). "
                    "Generate Tier 1 beginner Python assessments in admin first, "
                    "or use an existing database with bank content."
                )
            for bq in found:
                used_bank_ids.add(int(bq["bank_question_id"]))
                rows.append(_bank_row_to_snapshot_item(qid, bq))
                qid += 1

    if len(rows) != 25:
        raise RuntimeError(f"Expected 25 demo questions, got {len(rows)}")

    payload = {
        "version": 1,
        "language_code": MOCK_LANGUAGE_CODE,
        "language_label": MOCK_LANGUAGE_LABEL,
        "level": MOCK_LEVEL,
        "question_count": len(rows),
        "topic_names": topic_names,
        "questions": rows,
    }
    _SNAPSHOT_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {_SNAPSHOT_PATH.name} ({len(rows)} questions from question bank).")
    return rows


def load_questions_from_snapshot() -> tuple[list[dict[str, Any]], list[str]]:
    if not _SNAPSHOT_PATH.is_file():
        raise RuntimeError(
            f"Missing {_SNAPSHOT_PATH.name}. Run with --refresh-snapshot "
            "against a database that has Tier 1 beginner bank questions."
        )
    data = json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    rows = data.get("questions") or []
    if len(rows) != 25:
        raise RuntimeError(f"Snapshot must contain 25 questions, got {len(rows)}")
    topic_names = list(data.get("topic_names") or [])
    if not topic_names:
        topic_names = sorted(
            {str(r.get("topic_name") or "").strip() for r in rows if r.get("topic_name")}
        )
    out_rows: list[dict[str, Any]] = []
    for raw in rows:
        out_rows.append(
            {
                "question_id": str(raw["question_id"]),
                "question": raw["question"],
                "type": raw["type"],
                "options": raw.get("options") or "",
                "correct_answer": raw.get("correct_answer") or "",
                "topic_name": raw.get("topic_name") or "",
                "code_snippet": raw.get("code_snippet") or "",
                "difficulty": raw.get("difficulty") or MOCK_LEVEL,
            }
        )
    return out_rows, topic_names


def _user_label(employee_id: str, name: str) -> str:
    return f"{employee_id.strip()} | {name.strip()}"


def _wrong_mcq_answer(options_json: str) -> str:
    try:
        opts = json.loads(options_json)
        if isinstance(opts, list) and len(opts) > 1:
            correct = opts[0]
            for opt in opts[1:]:
                if str(opt) != str(correct):
                    return str(opt)
            return str(opts[1])
    except json.JSONDecodeError:
        pass
    return "Wrong option"


def _clear_student_data(
    assessment_id: str,
    employee_ids: list[str],
    bank_ids: set[int],
) -> None:
    """Remove prior demo submissions and mastery rows for a clean re-run."""
    eid_norms = {normalize_employee_id(eid) for eid in employee_ids}

    for sub in coll("submissions").find({"assessment_id": assessment_id}):
        uid = sub.get("user_id") or ""
        part = uid.split("|", 1)[0].strip().casefold()
        if part in eid_norms:
            coll("submissions").delete_one({"_id": sub["_id"]})

    if bank_ids:
        coll("employee_question_mastery").delete_many(
            {
                "employee_id": {"$in": list(eid_norms)},
                "bank_question_id": {"$in": list(bank_ids)},
            }
        )


def _reset_bank_stats(bank_ids: set[int]) -> None:
    if not bank_ids:
        return
    for bank_id in bank_ids:
        coll("question_bank").update_one(
            {"id": int(bank_id)},
            {"$set": {"times_correct": 0, "times_wrong": 0}},
        )


def _seed_assessment(rows: list[dict[str, Any]], topic_names: list[str]) -> set[int]:
    db_service.save_shared_assessment_rows(
        MOCK_ASSESSMENT_ID,
        rows,
        routing_flag="pyodide",
        language_code=MOCK_LANGUAGE_CODE,
        language_label=MOCK_LANGUAGE_LABEL,
        topic_names=topic_names,
        is_timed=False,
        allow_pyodide_paste=False,
    )

    hash_to_id = question_bank_service.add_questions_to_bank(
        rows, MOCK_LEVEL, MOCK_LANGUAGE_CODE
    )
    question_bank_service.link_assessment_questions_to_bank(
        MOCK_ASSESSMENT_ID, hash_to_id, MOCK_LEVEL
    )

    linked = db_service.read_questions_by_assessment(MOCK_ASSESSMENT_ID)
    return {
        int(r["bank_question_id"])
        for r in linked
        if r.get("bank_question_id") is not None
    }


def _seed_submissions(rows: list[dict[str, Any]]) -> None:
    for student in DEMO_STUDENTS:
        eid = student["employee_id"]
        name = student["name"]
        scores: list[float] = student["scores"]
        if len(scores) != len(rows):
            raise RuntimeError(
                f"Score count for {eid} ({len(scores)}) != questions ({len(rows)})"
            )

        user_id = _user_label(eid, name)
        ts = student["submitted_at"]

        for row, score in zip(rows, scores):
            qid = str(row["question_id"])
            qtype = (row.get("type") or "").lower()
            sc = round(float(score), 2)

            if qtype == "mcq":
                if sc >= SCORE_CORRECT_THRESHOLD:
                    answer = str(row.get("correct_answer") or "")
                else:
                    answer = _wrong_mcq_answer(str(row.get("options") or ""))
            else:
                answer = "# demo participant answer\npass"

            correct = _is_answer_correct(
                qtype,
                answer,
                str(row.get("correct_answer") or ""),
                sc,
            )
            feedback = (
                "Demo seed: strong answer."
                if correct
                else "Demo seed: review this topic and try again."
            )

            db_service.save_submission_row(
                MOCK_ASSESSMENT_ID,
                user_id,
                qid,
                answer,
                str(sc),
                feedback,
                ts,
                routing_flag="pyodide",
            )

            bank_id = row.get("bank_question_id")
            if bank_id is not None:
                question_bank_service.record_question_outcome(int(bank_id), correct)
                if correct:
                    question_bank_service.record_employee_question_mastery(
                        eid, int(bank_id)
                    )


def _attach_bank_ids(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stored = db_service.read_questions_by_assessment(MOCK_ASSESSMENT_ID)
    by_qid = {str(r["question_id"]): r for r in stored}
    enriched: list[dict[str, Any]] = []
    for row in rows:
        merged = dict(row)
        stored_row = by_qid.get(str(row["question_id"]))
        if stored_row:
            merged["bank_question_id"] = stored_row.get("bank_question_id")
        enriched.append(merged)
    return enriched


def _print_summary() -> None:
    print()
    print("=" * 72)
    print("Demo student data ready.")
    print("=" * 72)
    print(f"Assessment ID : {MOCK_ASSESSMENT_ID}")
    print(f"Title         : Tier 1 Beginner Python (25 questions, shared)")
    print(f"Language      : {MOCK_LANGUAGE_LABEL} ({MOCK_LANGUAGE_CODE})")
    print(f"Questions     : {_SNAPSHOT_PATH.name} (real bank content)")
    print()
    print("Students (employee ID | name → overall % on this assessment):")
    for student in DEMO_STUDENTS:
        scores = student["scores"]
        overall = round(sum(scores) / len(scores), 1) if scores else 0.0
        print(
            f"  {student['employee_id']} | {student['name']:<6} "
            f"→ {overall:5.1f}%  ({student['profile_note']})"
        )
    print()
    print("Try in the UI:")
    print("  /client  — enter employee ID + assessment ID above")
    print("  /client/my-report?employee_id=C00x")
    print("  /client/improve?employee_id=C00x")
    print("=" * 72)
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed demo students and assessment.")
    parser.add_argument(
        "--refresh-snapshot",
        action="store_true",
        help="Re-export demo_questions_snapshot.json from the live question bank.",
    )
    args = parser.parse_args()

    init_db()

    if args.refresh_snapshot:
        rows = export_snapshot_from_bank()
        topic_names = json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8")).get(
            "topic_names"
        ) or []
    else:
        rows, topic_names = load_questions_from_snapshot()

    employee_ids = [s["employee_id"] for s in DEMO_STUDENTS]

    existing_bank_ids: set[int] = set()
    if db_service.read_questions_by_assessment(MOCK_ASSESSMENT_ID):
        for r in db_service.read_questions_by_assessment(MOCK_ASSESSMENT_ID):
            bid = r.get("bank_question_id")
            if bid is not None:
                existing_bank_ids.add(int(bid))

    _clear_student_data(MOCK_ASSESSMENT_ID, employee_ids, existing_bank_ids)
    _reset_bank_stats(existing_bank_ids)

    _seed_assessment(rows, topic_names)
    enriched = _attach_bank_ids(rows)
    _seed_submissions(enriched)

    _print_summary()


if __name__ == "__main__":
    main()
