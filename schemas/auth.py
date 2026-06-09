"""Authentication request and response schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LoginBody(BaseModel):
    """Credentials for admin or client login."""

    role: Literal["admin", "client"] = Field(
        ...,
        description="Login role. `admin` requires `password`; `client` requires `client_id`.",
        examples=["admin"],
    )
    password: str | None = Field(
        default=None,
        description="Admin password (required when `role` is `admin`).",
        examples=["your-admin-password"],
    )
    client_id: str | None = Field(
        default=None,
        description=(
            "Participant client identifier (required when `role` is `client`). "
            "Letters, digits, underscore, and hyphen only; max 64 characters."
        ),
        examples=["participant-1"],
        max_length=64,
    )

    @model_validator(mode="after")
    def validate_login_fields(self) -> LoginBody:
        if self.role == "admin":
            if not (self.password or "").strip():
                raise ValueError("password is required for admin login")
        else:
            if not (self.client_id or "").strip():
                raise ValueError("client_id is required for client login")
        return self

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"role": "admin", "password": "your-admin-password"},
                {"role": "client", "client_id": "participant-1"},
            ]
        }
    )


class LoginResponse(BaseModel):
    """JWT access token issued after successful login."""

    access_token: str = Field(..., description="Bearer JWT access token.")
    token_type: Literal["bearer"] = Field("bearer", description="Token type (always `bearer`).")
    role: Literal["admin", "client"] = Field(..., description="Authenticated role.")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                    "token_type": "bearer",
                    "role": "admin",
                }
            ]
        }
    )


class ClientLoginResponse(LoginResponse):
    """JWT access token for a client participant, including their `client_id`."""

    client_id: str = Field(
        ...,
        description="Sanitized client identifier embedded in the token.",
        examples=["participant-1"],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                    "token_type": "bearer",
                    "role": "client",
                    "client_id": "participant-1",
                }
            ]
        }
    )
