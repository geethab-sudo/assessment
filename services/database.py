"""
MongoDB connection, indexes, and integer id sequences.

Set MONGODB_URI, e.g. mongodb+srv://user:pass@cluster.mongodb.net/assesment
Optional MONGODB_DB_NAME (default: assesment).
"""

from __future__ import annotations

import os
import re
import time
from typing import Any
from urllib.parse import urlparse

from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument
from pymongo.collection import Collection
from pymongo.database import Database

_client: MongoClient | None = None

COLLECTIONS = (
    "counters",
    "languages",
    "topics",
    "question_bank",
    "employee_question_mastery",
    "assessments",
    "assessment_questions",
    "assessment_attempts",
    "submissions",
    "certificates_issued",
    "platform_settings",
)


def get_mongodb_uri() -> str:
    """Read connection string from MONGODB_URI (preferred) or legacy MONGODB_URL."""
    for key in ("MONGODB_URI", "MONGODB_URL"):
        uri = (os.environ.get(key) or "").strip().strip('"').strip("'")
        if uri:
            return uri
    raise RuntimeError(
        "MONGODB_URI is not set. Example: "
        "mongodb+srv://user:pass@cluster.mongodb.net/assesment?retryWrites=true&w=majority"
    )


def get_database_name() -> str:
    explicit = (os.environ.get("MONGODB_DB_NAME") or "").strip()
    if explicit:
        return explicit
    uri = get_mongodb_uri()
    path = urlparse(uri).path.strip("/")
    if path:
        return path.split("/")[0]
    return "assesment"


def get_client() -> MongoClient:
    global _client
    if _client is None:
        kwargs: dict[str, Any] = {
            # Atlas free tier / cold clusters often need >10s on first connect.
            "serverSelectionTimeoutMS": 30_000,
            "connectTimeoutMS": 20_000,
        }
        try:
            import certifi

            kwargs["tlsCAFile"] = certifi.where()
        except ImportError:
            pass
        _client = MongoClient(get_mongodb_uri(), **kwargs)
    return _client


def reset_client() -> None:
    """Close the singleton client (used by tests when env or database name changes)."""
    global _client
    if _client is not None:
        _client.close()
        _client = None


def get_database() -> Database:
    return get_client()[get_database_name()]


def coll(name: str) -> Collection:
    return get_database()[name]


def next_id(counter_name: str) -> int:
    doc = coll("counters").find_one_and_update(
        {"_id": counter_name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return int(doc["seq"])


def sync_counter(counter_name: str, minimum: int) -> None:
    """Ensure a counter is at least ``minimum`` (used after PG migration)."""
    coll("counters").update_one(
        {"_id": counter_name},
        {"$max": {"seq": int(minimum)}},
        upsert=True,
    )


def _ensure_indexes() -> None:
    db = get_database()

    db.languages.create_index([("code", ASCENDING)], unique=True)

    db.topics.create_index([("language_id", ASCENDING), ("name", ASCENDING)], unique=True)
    db.topics.create_index([("name", ASCENDING)])

    db.question_bank.create_index([("content_hash", ASCENDING)], unique=True)
    db.question_bank.create_index([("language_code", ASCENDING)])
    db.question_bank.create_index([("difficulty", ASCENDING)])
    db.question_bank.create_index([("topic_name", ASCENDING), ("difficulty", ASCENDING)])

    db.employee_question_mastery.create_index(
        [("employee_id", ASCENDING), ("bank_question_id", ASCENDING)],
        unique=True,
    )
    db.employee_question_mastery.create_index([("employee_id", ASCENDING)])
    db.employee_question_mastery.create_index([("bank_question_id", ASCENDING)])

    db.assessments.create_index([("assessment_id", ASCENDING)], unique=True)
    db.assessments.create_index([("created_at", DESCENDING)])

    db.assessment_questions.create_index(
        [("assessment_id", ASCENDING), ("question_id", ASCENDING)],
        unique=True,
    )
    db.assessment_questions.create_index([("assessment_id", ASCENDING)])
    db.assessment_questions.create_index([("bank_question_id", ASCENDING)])

    db.assessment_attempts.create_index(
        [("assessment_id", ASCENDING), ("employee_id", ASCENDING)],
        unique=True,
    )
    db.assessment_attempts.create_index([("assessment_id", ASCENDING)])
    db.assessment_attempts.create_index([("employee_id", ASCENDING)])

    db.submissions.create_index([("assessment_id", ASCENDING), ("user_id", ASCENDING)])
    db.submissions.create_index([("timestamp", DESCENDING)])

    db.certificates_issued.create_index([("employee_id", ASCENDING)])
    db.certificates_issued.create_index([("assessment_id", ASCENDING)])

    db.platform_settings.create_index([("key", ASCENDING)], unique=True)


def _backfill_question_bank_difficulty_labels() -> None:
    mapping = {
        "easy": "beginner",
        "medium": "intermediate",
        "hard": "advanced",
    }
    for collection, field in (
        ("question_bank", "difficulty"),
        ("assessment_questions", "difficulty"),
    ):
        for old, new in mapping.items():
            coll(collection).update_many({field: old}, {"$set": {field: new}})


def _backfill_question_bank_from_assessment_questions_if_needed() -> None:
    if not coll("assessment_questions").find_one(
        {"bank_question_id": None},
        projection={"_id": 1},
    ):
        return
    from services import question_bank_service

    question_bank_service.backfill_question_bank_from_assessment_questions()


def _backfill_employee_question_mastery_if_empty() -> None:
    if coll("employee_question_mastery").find_one({}, projection={"_id": 1}):
        return
    from services import question_bank_service

    question_bank_service.backfill_employee_mastery_from_submissions()


def _wait_for_mongo(timeout_seconds: float = 45.0) -> None:
    """Retry ping until MongoDB is reachable (Atlas cold start / flaky first connect)."""
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            get_client().admin.command("ping")
            return
        except Exception as exc:
            last_error = exc
            time.sleep(2)
    raise RuntimeError(
        f"Could not connect to MongoDB within {timeout_seconds:.0f}s. "
        "Check MONGODB_URI, Atlas Network Access (allow your IP or 0.0.0.0/0), "
        "and that the cluster is not paused."
    ) from last_error


def init_db() -> None:
    """Create indexes and run one-time backfills (idempotent)."""
    _wait_for_mongo()
    _ensure_indexes()
    from services.catalog_seed import ensure_default_catalog

    ensure_default_catalog()
    from services.platform_settings_service import ensure_default_certificate_issuer_settings

    ensure_default_certificate_issuer_settings()
    _backfill_question_bank_difficulty_labels()
    _backfill_question_bank_from_assessment_questions_if_needed()
    _backfill_employee_question_mastery_if_empty()


def ping_database() -> bool:
    try:
        get_client().admin.command("ping")
        return True
    except Exception:
        return False


def doc_int_id(doc: dict[str, Any] | None) -> int | None:
    if not doc:
        return None
    value = doc.get("id")
    return int(value) if value is not None else None
