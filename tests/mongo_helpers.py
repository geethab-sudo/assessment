"""Helpers for MongoDB integration tests (Atlas ``test_db``)."""

from __future__ import annotations

from uuid import uuid4

from services import db_service
from services.database import COLLECTIONS, coll, next_id


TEST_DB_NAME = "test_db"


def unique_suffix() -> str:
    return uuid4().hex[:10]


def unique_assessment_id(prefix: str = "ASM-TEST") -> str:
    return f"{prefix}-{unique_suffix()}"


def clear_all_collections() -> None:
    """Remove all documents from app collections (indexes remain)."""
    from services.database import get_database_name

    db_name = get_database_name()
    if db_name != TEST_DB_NAME:
        raise RuntimeError(
            f"Refusing to clear MongoDB collections on database {db_name!r}. "
            f"Tests may only wipe {TEST_DB_NAME!r}. Check MONGODB_DB_NAME and pytest conftest."
        )
    for name in COLLECTIONS:
        coll(name).delete_many({})


def insert_test_topic(
    name: str,
    *,
    modality: str = "pyodide",
    language_id: int = 99_001,
) -> int:
    """Insert a catalog topic row for integration tests."""
    topic_id = next_id("topics")
    coll("topics").insert_one(
        {
            "id": topic_id,
            "language_id": language_id,
            "name": name,
            "modality": modality,
            "related_documents": [],
        }
    )
    return topic_id


def seed_report_fixture() -> tuple[str, str]:
    """
    Seed assessment + submissions for ``build_report`` integration tests.

    Returns ``(assessment_id, employee_id)``.
    """
    suffix = unique_suffix()
    assessment_id = f"ASM-REPORT-{suffix}"
    employee_id = f"E1001-{suffix}"
    user_id = f"{employee_id} | Jane Doe"

    oop_topic = f"OOP-{suffix}"
    jupyter_topic = f"Live API-{suffix}"
    insert_test_topic(oop_topic, modality="pyodide")
    insert_test_topic(jupyter_topic, modality="jupyter")

    rows = [
        {
            "question_id": "1",
            "question": "What is a class?",
            "type": "mcq",
            "options": '["A","B"]',
            "correct_answer": "A",
            "topic_name": oop_topic,
            "code_snippet": "",
        },
        {
            "question_id": "2",
            "question": "Write a function",
            "type": "coding",
            "options": "",
            "correct_answer": "",
            "topic_name": jupyter_topic,
            "code_snippet": "",
        },
        {
            "question_id": "3",
            "question": "Print hello",
            "type": "coding",
            "options": "",
            "correct_answer": "",
            "topic_name": oop_topic,
            "code_snippet": "",
        },
    ]
    db_service.save_shared_assessment_rows(
        assessment_id,
        rows,
        topic_names=[oop_topic, jupyter_topic],
        language_code="py",
        language_label="Python",
    )

    submissions = [
        ("1", "A", "100", "Correct.", "2026-06-08T10:00:00+00:00"),
        ("2", "import requests", "40", "Partial.", "2026-06-08T10:00:01+00:00"),
        ("3", "print('hi')", "80", "Good.", "2026-06-08T10:00:02+00:00"),
    ]
    for qid, answer, score, feedback, ts in submissions:
        db_service.save_submission_row(
            assessment_id,
            user_id,
            qid,
            answer,
            score,
            feedback,
            ts,
        )

    return assessment_id, employee_id
