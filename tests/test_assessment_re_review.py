"""Stage 13: admin assessment re-review, incremental save, publish, alias."""

from __future__ import annotations

import pytest

from services import assessment_service, db_service
from services.assessment_review_service import (
    assert_participant_may_load,
    create_review_draft,
    load_review_bundle,
    publish_review,
    save_review_question,
)
from services.database import coll
from tests.mongo_helpers import unique_assessment_id, unique_suffix


def _sample_question(qid: str = "1", **overrides) -> dict:
    base = {
        "question_id": qid,
        "type": "mcq",
        "question": f"What is 2+2? {unique_suffix()}",
        "code_snippet": "",
        "options": ["3", "4"],
        "correct_answer": "4",
        "topic_name": "Math",
    }
    base.update(overrides)
    return base


def test_create_review_draft_and_block_participant() -> None:
    draft = create_review_draft(
        {
            "topic": "Python basics",
            "level": "beginner",
            "language_code": "python",
            "topic_names": ["Math"],
        }
    )
    aid = draft["assessment_id"]
    assert draft["review_status"] == "draft"
    assert draft["question_count"] == 0

    with pytest.raises(ValueError, match="not published"):
        assert_participant_may_load(aid)

    out = assessment_service.get_assessment_for_user(aid)
    assert out["found"] is False

    admin_out = assessment_service.get_assessment_for_user(aid, allow_draft=True)
    assert admin_out["found"] is False


def test_create_review_draft_seeds_preview_questions() -> None:
    q = _sample_question()
    draft = create_review_draft(
        {
            "topic": "Python basics",
            "level": "beginner",
            "language_code": "python",
            "topic_names": ["Math"],
        },
        questions=[q],
    )
    assert draft["question_count"] == 1
    assert draft["questions"][0]["question"] == q["question"]
    assert draft["questions"][0].get("saved_at") is None

    bundle = load_review_bundle(draft["assessment_id"])
    assert bundle["question_count"] == 1
    assert bundle["questions"][0]["question"] == q["question"]


def test_save_review_question_and_publish() -> None:
    draft = create_review_draft(
        {
            "topic": "Python",
            "level": "beginner",
            "topic_names": ["Math"],
            "alias": "Test alias",
        }
    )
    aid = draft["assessment_id"]
    q = _sample_question()

    saved = save_review_question(aid, q["question_id"], q)
    assert saved["ok"] is True
    assert saved["saved_at"]
    assert saved["bank_question_id"] is not None

    bundle = load_review_bundle(aid)
    assert bundle["saved_count"] == 1
    assert bundle["questions"][0]["question"] == q["question"]
    assert bundle["alias"] == "Test alias"

    published = publish_review(aid, [q])
    assert published["review_status"] == "published"
    assert published["question_count"] == 1

    assert_participant_may_load(aid)
    participant = assessment_service.get_assessment_for_user(aid, employee_id="E-TEST")
    assert participant["found"] is True
    assert len(participant["questions"]) == 1


def test_save_edited_question_revises_id_when_submissions_exist() -> None:
    aid = unique_assessment_id()
    db_service.save_shared_assessment_rows(
        aid,
        [
            {
                "question_id": "1",
                "question": "Original?",
                "type": "mcq",
                "options": '["a","b"]',
                "correct_answer": "a",
                "topic_name": "T",
                "code_snippet": "",
            }
        ],
        topic="T",
        level="beginner",
        review_status="published",
    )
    employee_id = f"E-{unique_suffix()}"
    db_service.save_submission_row(
        aid,
        f"{employee_id} | Tester",
        "1",
        "a",
        "100",
        "OK",
        "2026-06-01T12:00:00+00:00",
    )

    edited = _sample_question("1", question="Edited question text?")
    result = save_review_question(aid, "1", edited)
    assert result["revised"] is True
    assert result["question_id"] != "1"

    old = coll("assessment_questions").find_one(
        {"assessment_id": aid, "question_id": "1"}
    )
    assert old is not None
    assert old.get("superseded_by") == result["question_id"]

    active = db_service.read_questions_by_assessment(aid)
    assert len(active) == 1
    assert active[0]["question_id"] == result["question_id"]
    assert "Edited" in active[0]["question"]


def test_list_assessments_summary_search_by_alias() -> None:
    suffix = unique_suffix()
    alias = f"Maria python exam {suffix}"
    draft = create_review_draft(
        {
            "topic": "Python",
            "level": "beginner",
            "topic_names": [],
            "alias": alias,
        }
    )
    rows = db_service.list_assessments_summary(search=alias)
    ids = [r["assessment_id"] for r in rows]
    assert draft["assessment_id"] in ids


def test_publish_accepts_empty_topic_when_topic_names_present() -> None:
    """Legacy assessments may lack topic; publish metadata should still validate."""
    from schemas.assessment_review import ReviewAssessmentMetadata

    meta = ReviewAssessmentMetadata.model_validate(
        {
            "topic": "",
            "level": "beginner",
            "topic_names": ["Python Basics", "Functions"],
        }
    )
    assert meta.topic == "Assessment"

    aid = unique_assessment_id()
    db_service.save_shared_assessment_rows(
        aid,
        [
            {
                "question_id": "1",
                "question": "Q?",
                "type": "mcq",
                "options": '["a","b"]',
                "correct_answer": "a",
                "topic_name": "Python Basics",
                "code_snippet": "",
            }
        ],
        topic_names=["Python Basics", "Functions"],
        review_status="published",
    )
    bundle = load_review_bundle(aid)
    assert bundle["topic"] == "Python Basics, Functions"





































