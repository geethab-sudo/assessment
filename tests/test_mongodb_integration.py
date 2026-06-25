"""MongoDB Atlas integration tests (database: ``test_db``).

Exercises real pymongo reads/writes for db_service, question_bank_service, and
report_service. Uses unique ids per test so data can persist in test_db between
runs without collisions.
"""

from __future__ import annotations

import pytest

from services import db_service
from services.database import coll, next_id, ping_database
from services.question_bank_service import (
    add_questions_to_bank,
    backfill_employee_mastery_from_submissions,
    backfill_question_bank_from_assessment_questions,
    find_bank_questions,
    get_bank_availability,
    get_bank_stats,
    get_employee_mastered_bank_ids,
    record_employee_question_mastery,
    record_question_outcome,
)
from services.report_service import build_report
from tests.mongo_helpers import (
    seed_report_fixture,
    unique_assessment_id,
    unique_suffix,
)


def test_ping_database_reaches_atlas() -> None:
    assert ping_database() is True


def test_next_id_increments_on_atlas() -> None:
    counter = f"test_counter_{unique_suffix()}"
    first = next_id(counter)
    second = next_id(counter)
    assert second == first + 1


def test_db_service_save_and_read_assessment() -> None:
    aid = unique_assessment_id()
    rows = [
        {
            "question_id": "1",
            "question": "2+2?",
            "type": "mcq",
            "options": '["3","4"]',
            "correct_answer": "4",
            "topic_name": "Math",
            "code_snippet": "",
        }
    ]
    db_service.save_shared_assessment_rows(
        aid,
        rows,
        topic_names=["Math"],
        language_code="py",
        language_label="Python",
    )
    loaded = db_service.read_questions_by_assessment(aid)
    assert len(loaded) == 1
    assert loaded[0]["question_id"] == "1"
    meta = db_service.get_assessment_metadata(aid)
    assert meta["language_code"] == "py"
    assert meta["topic_names"] == ["Math"]


def test_db_service_save_submission_and_list() -> None:
    aid = unique_assessment_id()
    db_service.save_shared_assessment_rows(
        aid,
        [
            {
                "question_id": "1",
                "question": "Q",
                "type": "mcq",
                "options": "",
                "correct_answer": "a",
                "topic_name": "T",
                "code_snippet": "",
            }
        ],
    )
    employee_id = f"E-{unique_suffix()}"
    user_id = f"{employee_id} | Test User"
    db_service.save_submission_row(
        aid, user_id, "1", "a", "100", "OK", "2026-06-01T12:00:00+00:00"
    )
    subs = db_service.get_participant_in_browser_submissions(aid, employee_id)
    assert len(subs) == 1
    assert subs[0]["score"] == "100"


def test_add_questions_to_bank_upserts_by_content_hash() -> None:
    suffix = unique_suffix()
    rows = [
        {
            "type": "mcq",
            "topic_name": f"Topic-{suffix}",
            "question": f"What is 2+2? {suffix}",
            "options": '["3","4"]',
            "correct_answer": "4",
        }
    ]
    first = add_questions_to_bank(rows, "beginner", "py")
    assert len(first) == 1
    second = add_questions_to_bank(rows, "beginner", "py")
    assert len(second) == 1
    bank_id = next(iter(first.values()))
    doc = coll("question_bank").find_one({"id": bank_id})
    assert doc is not None
    assert doc["times_used"] == 2
    assert doc["difficulty"] == "beginner"


def test_record_question_outcome_updates_bank() -> None:
    suffix = unique_suffix()
    bank_id = next(
        iter(
            add_questions_to_bank(
                [
                    {
                        "type": "mcq",
                        "topic_name": f"T-{suffix}",
                        "question": f"Q-{suffix}",
                        "options": "",
                        "correct_answer": "a",
                    }
                ],
                "beginner",
                "py",
            ).values()
        )
    )
    record_question_outcome(bank_id, True)
    record_question_outcome(bank_id, False)
    doc = coll("question_bank").find_one({"id": bank_id})
    assert doc["times_correct"] == 1
    assert doc["times_wrong"] == 1


def test_get_bank_stats_reads_from_atlas() -> None:
    suffix = unique_suffix()
    bank_id = next(
        iter(
            add_questions_to_bank(
                [
                    {
                        "type": "mcq",
                        "topic_name": f"Stats-{suffix}",
                        "question": f"Stats Q {suffix}",
                        "options": "",
                        "correct_answer": "a",
                    }
                ],
                "beginner",
                "py",
            ).values()
        )
    )
    coll("question_bank").update_one(
        {"id": bank_id},
        {"$set": {"times_correct": 3, "times_wrong": 1}},
    )
    stats = get_bank_stats(difficulty="beginner")
    match = [s for s in stats if s["id"] == bank_id]
    assert len(match) == 1
    assert match[0]["percent_correct"] == 75.0


def test_find_bank_questions_filters_topic() -> None:
    suffix = unique_suffix()
    topic = f"Filter-{suffix}"
    add_questions_to_bank(
        [
            {
                "type": "mcq",
                "topic_name": topic,
                "question": f"Find me {suffix}",
                "options": "",
                "correct_answer": "a",
            }
        ],
        "beginner",
        "py",
    )
    found, shortage = find_bank_questions([topic], "beginner", 5)
    assert len(found) == 1
    assert found[0]["topic_name"] == topic
    assert shortage == 4


def test_employee_mastery_insert_and_lookup() -> None:
    employee_id = f"E-{unique_suffix()}"
    suffix = unique_suffix()
    bank_id = next(
        iter(
            add_questions_to_bank(
                [
                    {
                        "type": "mcq",
                        "topic_name": f"Mastery-{suffix}",
                        "question": f"Mastery Q {suffix}",
                        "options": "",
                        "correct_answer": "a",
                    }
                ],
                "beginner",
                "py",
            ).values()
        )
    )
    record_employee_question_mastery(employee_id, bank_id)
    record_employee_question_mastery(employee_id, bank_id)
    mastered = get_employee_mastered_bank_ids(employee_id)
    assert mastered == {bank_id}


def test_get_bank_availability_excludes_mastered() -> None:
    employee_id = f"E-{unique_suffix()}"
    suffix = unique_suffix()
    topic = f"Avail-{suffix}"
    ids = []
    for i in range(3):
        ids.append(
            next(
                iter(
                    add_questions_to_bank(
                        [
                            {
                                "type": "mcq",
                                "topic_name": topic,
                                "question": f"Avail {suffix} #{i}",
                                "options": "",
                                "correct_answer": "a",
                            }
                        ],
                        "beginner",
                        "py",
                    ).values()
                )
            )
        )
    record_employee_question_mastery(employee_id, ids[0])
    result = get_bank_availability(
        [topic], "beginner", 5, exclude_employee_id=employee_id
    )
    assert result["available"] == 2
    assert result["shortage"] == 3


def test_backfill_question_bank_links_assessment_questions(mongo_clean) -> None:
    aid = unique_assessment_id()
    db_service.save_shared_assessment_rows(
        aid,
        [
            {
                "question_id": "1",
                "question": "What is 1+1?",
                "type": "mcq",
                "options": '["1","2"]',
                "correct_answer": "2",
                "topic_name": "",
                "code_snippet": "",
                "bank_question_id": None,
                "difficulty": None,
            }
        ],
        topic_names=["Tier 1 - Topic A"],
        language_code="py",
    )
    linked = backfill_question_bank_from_assessment_questions()
    assert linked == 1
    aq = coll("assessment_questions").find_one({"assessment_id": aid})
    assert aq["bank_question_id"] is not None
    assert aq["difficulty"] == "beginner"


def test_backfill_employee_mastery_from_submissions(mongo_clean) -> None:
    aid = unique_assessment_id()
    employee_id = f"E-{unique_suffix()}"
    user_id = f"{employee_id} | Alice"
    db_service.save_shared_assessment_rows(
        aid,
        [
            {
                "question_id": "1",
                "question": "coding",
                "type": "coding",
                "options": "",
                "correct_answer": "",
                "topic_name": "T",
                "code_snippet": "",
                "bank_question_id": 10,
            },
            {
                "question_id": "2",
                "question": "mcq",
                "type": "mcq",
                "options": "",
                "correct_answer": "four",
                "topic_name": "T",
                "code_snippet": "",
                "bank_question_id": 20,
            },
        ],
    )
    db_service.save_submission_row(
        aid, user_id, "1", "wrong", "40", "no", "2026-01-01T00:00:00+00:00"
    )
    db_service.save_submission_row(
        aid, user_id, "2", "four", "100", "yes", "2026-01-02T00:00:00+00:00"
    )
    n = backfill_employee_mastery_from_submissions()
    assert n == 1
    row = coll("employee_question_mastery").find_one(
        {"employee_id": employee_id.lower(), "bank_question_id": 20}
    )
    assert row is not None


def test_build_report_joins_submissions_and_skips_jupyter_coding() -> None:
    assessment_id, employee_id = seed_report_fixture()
    report = build_report(assessment_id, employee_id)
    assert report["participant"]["employee_id"] == employee_id
    assert report["participant"]["name"] == "Jane Doe"
    assert report["overall_score"] == 90.0
    assert report["questions_graded"] == 2
    assert [q["question_id"] for q in report["questions"]] == ["1", "3"]
    assert report["topic_summary"][0]["topic_name"].startswith("OOP-")
    assert report["report_scope"] == "in_browser"


def test_build_report_raises_when_no_submission() -> None:
    aid = unique_assessment_id()
    db_service.save_shared_assessment_rows(
        aid,
        [
            {
                "question_id": "1",
                "question": "Q",
                "type": "mcq",
                "options": "",
                "correct_answer": "a",
                "topic_name": "T",
                "code_snippet": "",
            }
        ],
    )
    with pytest.raises(ValueError, match="No submission found"):
        build_report(aid, f"E-missing-{unique_suffix()}")
