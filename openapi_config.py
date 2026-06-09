"""OpenAPI metadata: tags, security schemes, and shared response definitions."""

from __future__ import annotations

from typing import Any

from schemas.common import ErrorDetail, ValidationErrorResponse

OPENAPI_TAGS: list[dict[str, str]] = [
    {
        "name": "health",
        "description": "Service health and configuration probes.",
    },
    {
        "name": "auth",
        "description": (
            "Issue JWT bearer tokens for **admin** (password) or **client** (client_id) roles. "
            "Admin tokens are required for mutating `/admin/*` routes and `POST /generate-assessment`."
        ),
    },
    {
        "name": "catalog",
        "description": "Public read-only access to programming language catalog metadata.",
    },
    {
        "name": "assessments",
        "description": (
            "Participant-facing assessment retrieval, answer submission, and Jupyter notebook upload. "
            "Most routes are public for shared assessments; client-scoped assessments may require "
            "the optional `client_id` header."
        ),
    },
    {
        "name": "admin",
        "description": (
            "Administrative operations: generate assessments, manage catalog, list submissions. "
            "GET routes are public; POST, PUT, and DELETE require `Authorization: Bearer <admin_jwt>`."
        ),
    },
]

API_DESCRIPTION = """
AI-powered technical assessment platform API.

## Authentication

| Role | How to authenticate | Used for |
|------|---------------------|----------|
| **Admin** | `POST /auth/login` with `role: admin` and `password` | Mutating `/admin/*` routes and `POST /generate-assessment` |
| **Client** | `POST /auth/login` with `role: client` and `client_id` | Optional; required only for client-scoped assessments |
| **Public** | No token | Shared assessments, catalog, health |

Send admin tokens as: `Authorization: Bearer <access_token>`

## Assessment access

- **Shared assessments** (`owner_client_id` is null): any caller may fetch and submit.
- **Client-scoped assessments**: pass matching `client_id` in the `client_id` request header
  on notebook routes; open-access web UI uses shared assessments only.

## Error format

Most errors return `{"detail": "<message>"}`. Validation errors (HTTP 422) return
`{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}`.
""".strip()


def _error_response(description: str, example: str) -> dict[str, Any]:
    return {
        "description": description,
        "content": {
            "application/json": {
                "schema": ErrorDetail.model_json_schema(),
                "example": {"detail": example},
            }
        },
    }


ERROR_400 = _error_response("Bad request — invalid input or business rule violation.", "Invalid assessment ID format")
ERROR_401 = _error_response("Missing or invalid bearer token.", "Not authenticated")
ERROR_403 = _error_response("Authenticated but not permitted for this resource.", "Admin access required")
ERROR_404 = _error_response("Resource not found.", "Assessment not found")
ERROR_409 = _error_response("Request conflicts with current resource state.", "This assessment expects notebook coding questions, but none are available in the template.")
ERROR_413 = _error_response("Uploaded payload exceeds size limit.", "File too large (max 5 MiB)")
ERROR_422: dict[str, Any] = {
    "description": "Request validation failed (Pydantic).",
    "content": {
        "application/json": {
            "schema": {"$ref": "#/components/schemas/ValidationErrorResponse"},
            "example": {
                "detail": [
                    {
                        "loc": ["body", "level"],
                        "msg": "level must be one of: beginner, intermediate, advanced",
                        "type": "value_error",
                    }
                ]
            },
        }
    },
}
ERROR_500 = _error_response("Unexpected server error.", "Internal server error")
ERROR_503 = _error_response("Required service or configuration unavailable.", "GROQ API key is not configured")


def auth_error_responses(*, include_403: bool = False) -> dict[int, dict[str, Any]]:
    """401 (and optionally 403) responses for admin-protected routes."""
    out: dict[int, dict[str, Any]] = {401: ERROR_401}
    if include_403:
        out[403] = ERROR_403
    return out


def public_assessment_errors() -> dict[int, dict[str, Any]]:
    return {
        400: ERROR_400,
        403: ERROR_403,
        404: ERROR_404,
        422: ERROR_422,
        500: ERROR_500,
    }


def admin_crud_errors(*, include_404: bool = True, include_auth: bool = True) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    if include_auth:
        out.update(auth_error_responses(include_403=True))
    out.update(
        {
            400: ERROR_400,
            422: ERROR_422,
            500: ERROR_500,
        }
    )
    if include_404:
        out[404] = ERROR_404
    return out
