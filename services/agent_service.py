"""CRUD helpers for LLM agent/provider configuration."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from services.database import get_session_factory
from services.models import Agent

ALLOWED_AGENT_NAMES = frozenset({"groq", "claude", "openai", "gemini"})
AGENT_STATUS_ACTIVE = "Active"
AGENT_STATUS_INACTIVE = "Inactive"
VALID_STATUSES = frozenset({AGENT_STATUS_ACTIVE, AGENT_STATUS_INACTIVE})


def _session() -> Session:
    return get_session_factory()()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_agent_name(name: str) -> str:
    return name.strip().lower()


def _normalize_api_key(raw: str | None) -> str:
    if raw is None:
        return ""
    return raw.strip().strip('"').strip("'").strip()


def _mask_api_key(key: str) -> str:
    key = key.strip()
    if not key:
        return ""
    if len(key) <= 8:
        return "••••••••"
    return f"{'•' * 12}{key[-4:]}"


def _agent_to_dict(row: Agent, *, mask_key: bool = True) -> dict[str, Any]:
    key = row.api_key or ""
    return {
        "id": row.id,
        "agent_name": row.agent_name,
        "status": row.status,
        "is_selected": row.is_selected,
        "api_key_masked": _mask_api_key(key) if mask_key else key,
        "api_key_configured": bool(key),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def list_agents() -> list[dict[str, Any]]:
    with _session() as session:
        rows = session.scalars(select(Agent).order_by(Agent.agent_name)).all()
        return [_agent_to_dict(r) for r in rows]


def get_agent(agent_id: int) -> dict[str, Any] | None:
    with _session() as session:
        row = session.get(Agent, agent_id)
        if not row:
            return None
        return _agent_to_dict(row)


def get_selected_agent() -> dict[str, Any] | None:
    """Return the selected active agent with unmasked api_key (for LLM calls)."""
    with _session() as session:
        row = session.scalar(
            select(Agent).where(
                Agent.is_selected.is_(True),
                Agent.status == AGENT_STATUS_ACTIVE,
            )
        )
        if not row:
            return None
        return _agent_to_dict(row, mask_key=False)


def create_agent(*, agent_name: str, api_key: str) -> dict[str, Any]:
    name = _normalize_agent_name(agent_name)
    if name not in ALLOWED_AGENT_NAMES:
        raise ValueError(
            f"agent_name must be one of: {', '.join(sorted(ALLOWED_AGENT_NAMES))}"
        )
    key = _normalize_api_key(api_key)
    if not key:
        raise ValueError("api_key is required")
    now = _utc_now()
    with _session() as session:
        if session.scalar(select(Agent).where(Agent.agent_name == name)):
            raise ValueError(f"Agent {name!r} already exists")
        is_first = session.scalar(select(Agent.id).limit(1)) is None
        row = Agent(
            agent_name=name,
            api_key=key,
            status=AGENT_STATUS_ACTIVE,
            is_selected=is_first,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _agent_to_dict(row)


def update_agent(
    *,
    agent_id: int,
    agent_name: str | None = None,
    api_key: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    with _session() as session:
        row = session.get(Agent, agent_id)
        if not row:
            raise ValueError("Agent not found")

        if agent_name is not None:
            name = _normalize_agent_name(agent_name)
            if name not in ALLOWED_AGENT_NAMES:
                raise ValueError(
                    f"agent_name must be one of: {', '.join(sorted(ALLOWED_AGENT_NAMES))}"
                )
            if name != row.agent_name and session.scalar(
                select(Agent).where(Agent.agent_name == name, Agent.id != agent_id)
            ):
                raise ValueError(f"Agent {name!r} already exists")
            row.agent_name = name

        if api_key is not None:
            key = _normalize_api_key(api_key)
            if not key:
                raise ValueError("api_key cannot be empty")
            row.api_key = key

        if status is not None:
            st = status.strip()
            if st not in VALID_STATUSES:
                raise ValueError("status must be Active or Inactive")
            if st == AGENT_STATUS_INACTIVE and row.is_selected:
                raise ValueError(
                    "Cannot deactivate the currently selected agent. Select another agent first."
                )
            row.status = st

        row.updated_at = _utc_now()
        session.commit()
        session.refresh(row)
        return _agent_to_dict(row)


def select_agent(*, agent_id: int) -> dict[str, Any]:
    with _session() as session:
        row = session.get(Agent, agent_id)
        if not row:
            raise ValueError("Agent not found")
        if row.status != AGENT_STATUS_ACTIVE:
            raise ValueError("Only Active agents can be selected")
        if not (row.api_key or "").strip():
            raise ValueError("Agent must have an API key configured")

        session.execute(update(Agent).values(is_selected=False))
        row.is_selected = True
        row.updated_at = _utc_now()
        session.commit()
        session.refresh(row)
        return _agent_to_dict(row)


def seed_default_agent_from_env() -> None:
    """If no agents exist, seed Groq from GROQ_API_KEY when present."""
    key = _normalize_api_key(os.environ.get("GROQ_API_KEY"))
    if not key:
        return
    with _session() as session:
        if session.scalar(select(Agent.id).limit(1)) is not None:
            return
        now = _utc_now()
        session.add(
            Agent(
                agent_name="groq",
                api_key=key,
                status=AGENT_STATUS_ACTIVE,
                is_selected=True,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()
