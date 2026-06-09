"""Shared OpenAPI response models and error schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ErrorDetail(BaseModel):
    """Standard HTTP error body returned by ``HTTPException``."""

    detail: str = Field(
        ...,
        description="Human-readable error message.",
        examples=["Assessment not found"],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"detail": "Assessment not found"},
                {"detail": "Not authenticated"},
                {"detail": "Admin access required"},
            ]
        }
    )


class ValidationErrorItem(BaseModel):
    """Single field-level validation failure (HTTP 422)."""

    loc: list[str | int] = Field(
        ...,
        description="Location of the error (e.g. `['body', 'level']`).",
    )
    msg: str = Field(..., description="Validation error message.")
    type: str = Field(..., description="Pydantic error type identifier.")


class ValidationErrorResponse(BaseModel):
    """Request body or parameter validation failed (HTTP 422)."""

    detail: list[ValidationErrorItem]

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "detail": [
                        {
                            "loc": ["body", "level"],
                            "msg": "level must be one of: beginner, intermediate, advanced",
                            "type": "value_error",
                        }
                    ]
                }
            ]
        }
    )


class OkDeletedResponse(BaseModel):
    """Generic success response for delete operations."""

    ok: bool = Field(True, description="Always `true` on success.")
    deleted: str | int = Field(..., description="Identifier of the deleted resource.")

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"ok": True, "deleted": "550e8400-e29b-41d4-a716-446655440000"}]}
    )


class HealthResponse(BaseModel):
    """Service health and configuration flags."""

    status: str = Field("ok", description="Overall service status.")
    database: bool = Field(..., description="Whether the database connection is reachable.")
    groq_configured: bool = Field(
        ...,
        description="Whether `GROQ_API_KEY` is set for LLM question generation and grading.",
    )
    auth_configured: bool = Field(
        ...,
        description="Whether both `JWT_SECRET` and `ADMIN_PASSWORD` are configured.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "ok",
                    "database": True,
                    "groq_configured": True,
                    "auth_configured": True,
                }
            ]
        }
    )
