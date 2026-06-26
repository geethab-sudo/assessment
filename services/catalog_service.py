"""CRUD helpers for languages and topics (reference catalog)."""

from __future__ import annotations

from typing import Any

from pymongo.errors import DuplicateKeyError

from services.database import coll, next_id


def list_languages() -> list[dict[str, Any]]:
    rows = list(coll("languages").find().sort("code", 1))
    return [{"id": r["id"], "code": r["code"], "name": r["name"]} for r in rows]


def create_language(*, code: str, name: str) -> dict[str, Any]:
    code = code.strip()
    name = name.strip()
    if not code or not name:
        raise ValueError("code and name are required")
    if coll("languages").find_one({"code": code}, projection={"_id": 1}):
        raise ValueError("Language with this code already exists")
    row = {"id": next_id("languages"), "code": code, "name": name}
    coll("languages").insert_one(row)
    return {"id": row["id"], "code": row["code"], "name": row["name"]}


def update_language(*, language_id: int, code: str, name: str) -> dict[str, Any]:
    code = code.strip()
    name = name.strip()
    if not code or not name:
        raise ValueError("code and name are required")
    row = coll("languages").find_one({"id": int(language_id)})
    if not row:
        raise ValueError("Language not found")
    if code != row["code"] and coll("languages").find_one(
        {"code": code, "id": {"$ne": int(language_id)}},
        projection={"_id": 1},
    ):
        raise ValueError("Language with this code already exists")
    coll("languages").update_one(
        {"id": int(language_id)},
        {"$set": {"code": code, "name": name}},
    )
    return {"id": int(language_id), "code": code, "name": name}


def get_language(language_id: int) -> dict[str, Any] | None:
    row = coll("languages").find_one({"id": int(language_id)})
    if not row:
        return None
    return {"id": row["id"], "code": row["code"], "name": row["name"]}


def list_topics(*, language_id: int | None = None) -> list[dict[str, Any]]:
    query: dict[str, Any] = {}
    if language_id is not None:
        query["language_id"] = int(language_id)
    rows = list(
        coll("topics").find(query).sort([("language_id", 1), ("id", 1)])
    )
    return [
        {
            "id": r["id"],
            "language_id": r["language_id"],
            "name": r["name"],
            "related_documents": r.get("related_documents") or [],
        }
        for r in rows
    ]


def create_topic(
    *,
    language_id: int,
    name: str,
    related_documents: list[dict[str, Any]],
) -> dict[str, Any]:
    name = name.strip()
    if not name:
        raise ValueError("name is required")
    if not coll("languages").find_one({"id": int(language_id)}, projection={"_id": 1}):
        raise ValueError("language_id does not exist")
    row = {
        "id": next_id("topics"),
        "language_id": int(language_id),
        "name": name,
        "related_documents": related_documents,
        "modality": "pyodide",
        "coding_editor_language": None,
    }
    try:
        coll("topics").insert_one(row)
    except DuplicateKeyError:
        raise ValueError(
            "A topic with this name already exists for that language"
        ) from None
    return {
        "id": row["id"],
        "language_id": row["language_id"],
        "name": row["name"],
        "related_documents": row["related_documents"],
    }


def update_topic(
    *,
    topic_id: int,
    language_id: int,
    name: str,
    related_documents: list[dict[str, Any]],
) -> dict[str, Any]:
    name = name.strip()
    if not name:
        raise ValueError("name is required")
    if not coll("topics").find_one({"id": int(topic_id)}, projection={"_id": 1}):
        raise ValueError("Topic not found")
    if not coll("languages").find_one({"id": int(language_id)}, projection={"_id": 1}):
        raise ValueError("language_id does not exist")
    try:
        coll("topics").update_one(
            {"id": int(topic_id)},
            {
                "$set": {
                    "language_id": int(language_id),
                    "name": name,
                    "related_documents": related_documents,
                }
            },
        )
    except DuplicateKeyError:
        raise ValueError(
            "A topic with this name already exists for that language"
        ) from None
    return {
        "id": int(topic_id),
        "language_id": int(language_id),
        "name": name,
        "related_documents": related_documents,
    }


def delete_topic(*, topic_id: int) -> None:
    result = coll("topics").delete_one({"id": int(topic_id)})
    if result.deleted_count == 0:
        raise ValueError("Topic not found")
