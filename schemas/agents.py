"""Pydantic schemas for LLM agent/provider management."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from services.agent_service import ALLOWED_AGENT_NAMES, VALID_STATUSES

AgentStatus = Literal["Active", "Inactive"]


class AgentOut(BaseModel):
    """Agent row as returned by the admin API (API key is masked)."""

    id: int
    agent_name: str = Field(..., description="Provider id: groq, claude, openai, or gemini.")
    status: AgentStatus
    is_selected: bool = Field(..., description="Whether this agent is used for all LLM calls.")
    api_key_masked: str = Field(..., description="Masked API key for display.")
    api_key_configured: bool
    created_at: str
    updated_at: str


class AgentsResponse(BaseModel):
    agents: list[AgentOut]
    supported_providers: list[str] = Field(
        default_factory=lambda: sorted(ALLOWED_AGENT_NAMES),
        description="Provider names that can be added.",
    )


class AgentResponse(BaseModel):
    agent: AgentOut


class AgentCreateBody(BaseModel):
    agent_name: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Provider: groq, claude, openai, or gemini.",
        examples=["groq"],
    )
    api_key: str = Field(..., min_length=1, description="API key for the provider.")

    @field_validator("agent_name", mode="before")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        return v.strip().lower() if isinstance(v, str) else v


class AgentUpdateBody(BaseModel):
    agent_name: str | None = Field(default=None, max_length=64)
    api_key: str | None = Field(default=None, min_length=1)
    status: AgentStatus | None = None

    @field_validator("agent_name", mode="before")
    @classmethod
    def normalize_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if v not in VALID_STATUSES:
            raise ValueError("status must be Active or Inactive")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"api_key": "sk-new-key-here"},
                {"status": "Inactive"},
            ]
        }
    )
