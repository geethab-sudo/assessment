"""CRUD helpers for languages and topics (reference catalog)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from services.database import get_session_factory
from services.models import Language, Topic


def _session() -> Session:
    return get_session_factory()()


def list_languages() -> list[dict[str, Any]]:
    with _session() as session:
        rows = session.scalars(select(Language).order_by(Language.code)).all()
        return [{"id": r.id, "code": r.code, "name": r.name} for r in rows]


def create_language(*, code: str, name: str) -> dict[str, Any]:
    code = code.strip()
    name = name.strip()
    if not code or not name:
        raise ValueError("code and name are required")
    with _session() as session:
        if session.scalar(select(Language).where(Language.code == code)):
            raise ValueError("Language with this code already exists")
        row = Language(code=code, name=name)
        session.add(row)
        session.commit()
        session.refresh(row)
        return {"id": row.id, "code": row.code, "name": row.name}


def update_language(*, language_id: int, code: str, name: str) -> dict[str, Any]:
    code = code.strip()
    name = name.strip()
    if not code or not name:
        raise ValueError("code and name are required")
    with _session() as session:
        row = session.get(Language, language_id)
        if not row:
            raise ValueError("Language not found")
        if code != row.code and session.scalar(
            select(Language).where(
                Language.code == code, Language.id != language_id
            )
        ):
            raise ValueError("Language with this code already exists")
        row.code = code
        row.name = name
        session.commit()
        session.refresh(row)
        return {"id": row.id, "code": row.code, "name": row.name}


def get_language(language_id: int) -> dict[str, Any] | None:
    with _session() as session:
        row = session.get(Language, language_id)
        if not row:
            return None
        return {"id": row.id, "code": row.code, "name": row.name}


def list_topics(*, language_id: int | None = None) -> list[dict[str, Any]]:
    with _session() as session:
        q = select(Topic)
        if language_id is not None:
            q = q.where(Topic.language_id == language_id)
        rows = session.scalars(q.order_by(Topic.language_id, Topic.id)).all()
        return [
            {
                "id": r.id,
                "language_id": r.language_id,
                "name": r.name,
                "related_documents": r.related_documents or [],
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
    with _session() as session:
        if not session.get(Language, language_id):
            raise ValueError("language_id does not exist")
        row = Topic(
            language_id=language_id,
            name=name,
            related_documents=related_documents,
        )
        session.add(row)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise ValueError(
                "A topic with this name already exists for that language"
            ) from None
        session.refresh(row)
        return {
            "id": row.id,
            "language_id": row.language_id,
            "name": row.name,
            "related_documents": row.related_documents or [],
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
    with _session() as session:
        row = session.get(Topic, topic_id)
        if not row:
            raise ValueError("Topic not found")
        if not session.get(Language, language_id):
            raise ValueError("language_id does not exist")
        row.language_id = language_id
        row.name = name
        row.related_documents = related_documents
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            raise ValueError(
                "A topic with this name already exists for that language"
            ) from None
        session.refresh(row)
        return {
            "id": row.id,
            "language_id": row.language_id,
            "name": row.name,
            "related_documents": row.related_documents or [],
        }


def delete_topic(*, topic_id: int) -> None:
    """Remove a topic row. Raises ValueError if the id does not exist."""
    with _session() as session:
        row = session.get(Topic, topic_id)
        if not row:
            raise ValueError("Topic not found")
        session.delete(row)
        session.commit()
