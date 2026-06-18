"""
FastAPI application: AI assessment generation, retrieval, and graded submission.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from dotenv import load_dotenv

# Load `.env` next to this file first so GROQ_API_KEY is set even if the shell cwd differs.
_root = Path(__file__).resolve().parent
load_dotenv(_root / ".env", override=True)
load_dotenv(override=True)

import json

from fastapi import FastAPI, File, Form, Header, HTTPException, Path, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from middleware.rate_limit import RateLimitMiddleware
from middleware.security_headers import SecurityHeadersMiddleware

from openapi_config import (
    API_DESCRIPTION,
    ERROR_400,
    ERROR_401,
    ERROR_413,
    ERROR_422,
    ERROR_500,
    ERROR_503,
    OPENAPI_TAGS,
    public_assessment_errors,
)
from routers.admin import admin_ops_router, admin_router
from schemas.assessment import (
    AssessmentResponse,
    NotebookSubmitResponse,
    SubmitAssessmentBody,
    SubmitAssessmentResponse,
)
from schemas.auth import ClientLoginResponse, LoginBody, LoginResponse
from schemas.catalog import LanguagesResponse
from schemas.common import ErrorDetail, HealthResponse, ValidationErrorItem, ValidationErrorResponse
from schemas.improvement import (
    DifficultyImprovementRequest,
    DifficultyImprovementResponse,
    EmployeeProfileResponse,
    EmployeeReportResponse,
    NewAreasImprovementRequest,
    NewAreasImprovementResponse,
    WeakAreasImprovementRequest,
    WeakAreasImprovementResponse,
)
from services import assessment_service, audit_log, auth_service, catalog_service, notebook_service, report_service
from services import db_service, employee_profile_service, improvement_assessment_service
from services.attempt_service import TimedAssessmentError
from services.database import init_db, ping_database
from services.llm_service import groq_key_configured

MAX_NOTEBOOK_BYTES = 5 * 1024 * 1024  # 5 MiB


def _require_valid_assessment_id(raw: str) -> str:
    """Strip and validate assessment id (legacy UUID or ASM-XXXXXXXX). Raises HTTPException."""
    from services.ids import normalize_assessment_id

    try:
        return normalize_assessment_id(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid assessment ID format") from None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    audit_log.configure_audit_logging()
    init_db()
    yield


app = FastAPI(
    title="AI Assessment API",
    version="1.0.0",
    description=API_DESCRIPTION,
    lifespan=lifespan,
    openapi_tags=OPENAPI_TAGS,
    swagger_ui_parameters={"docExpansion": "list", "defaultModelsExpandDepth": 2},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)


def custom_openapi() -> dict[str, Any]:
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=OPENAPI_TAGS,
    )
    components = schema.setdefault("components", {})
    components.setdefault("securitySchemes", {})["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": (
            "JWT from `POST /auth/login`. Use an **admin** token for mutating "
            "`/admin/*` routes and `POST /generate-assessment`."
        ),
    }
    extra_schemas = components.setdefault("schemas", {})
    ref = "#/components/schemas/{model}"
    extra_schemas["ErrorDetail"] = ErrorDetail.model_json_schema(ref_template=ref)
    extra_schemas["ValidationErrorItem"] = ValidationErrorItem.model_json_schema(ref_template=ref)
    extra_schemas["ValidationErrorResponse"] = ValidationErrorResponse.model_json_schema(ref_template=ref)
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi  # type: ignore[method-assign]

app.include_router(admin_router)
app.include_router(admin_ops_router)


@app.get(
    "/health",
    tags=["health"],
    summary="Health check",
    response_model=HealthResponse,
    responses={
        200: {
            "description": "Service is running.",
            "content": {
                "application/json": {
                    "example": {
                        "status": "ok",
                        "database": True,
                        "groq_configured": True,
                        "auth_configured": True,
                    }
                }
            },
        }
    },
)
def health() -> HealthResponse:
    """
    Returns service status and whether critical environment variables are configured.

    Does not require authentication. Use for load-balancer probes and deployment checks.
    """
    return HealthResponse(
        status="ok",
        database=ping_database(),
        groq_configured=groq_key_configured(),
        auth_configured=bool(
            auth_service.jwt_configured() and auth_service.admin_password_configured()
        ),
    )


@app.post(
    "/auth/login",
    tags=["auth"],
    summary="Obtain JWT access token",
    response_model=LoginResponse | ClientLoginResponse,
    responses={
        200: {
            "description": "Authentication successful; bearer token issued.",
            "content": {
                "application/json": {
                    "examples": {
                        "admin": {
                            "summary": "Admin login",
                            "value": {
                                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                                "token_type": "bearer",
                                "role": "admin",
                            },
                        },
                        "client": {
                            "summary": "Client login",
                            "value": {
                                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                                "token_type": "bearer",
                                "role": "client",
                                "client_id": "participant-1",
                            },
                        },
                    }
                }
            },
        },
        400: ERROR_400,
        401: {
            "description": "Invalid admin password.",
            "content": {
                "application/json": {
                    "example": {"detail": "Invalid credentials"},
                }
            },
        },
        422: ERROR_422,
        503: ERROR_503,
    },
)
def login(request: Request, body: LoginBody) -> LoginResponse | ClientLoginResponse:
    """
    Authenticate as **admin** or **client** and receive a JWT bearer token.

    - **Admin**: requires `password` matching `ADMIN_PASSWORD` in server `.env`.
    - **Client**: requires `client_id` (alphanumeric, `_`, `-`; max 64 chars).

    Neither role is required for public shared-assessment routes.
    """
    if body.role == "admin":
        if not auth_service.admin_password_configured():
            audit_log.auth_login_failure(request, role="admin", reason="admin_not_configured")
            raise HTTPException(
                status_code=503,
                detail="Admin login is not configured. Set ADMIN_PASSWORD in the server .env file.",
            )
        if not auth_service.jwt_configured():
            audit_log.auth_login_failure(request, role="admin", reason="jwt_not_configured")
            raise HTTPException(
                status_code=503,
                detail="JWT_SECRET is not set in the server .env file.",
            )
        if not auth_service.verify_admin_password(body.password or ""):
            audit_log.auth_login_failure(request, role="admin", reason="invalid_credentials")
            raise HTTPException(status_code=401, detail="Invalid credentials")
        token = auth_service.create_access_token("admin")
        audit_log.auth_login_success(request, role="admin")
        return LoginResponse(access_token=token, token_type="bearer", role="admin")

    if not auth_service.jwt_configured():
        audit_log.auth_login_failure(request, role="client", reason="jwt_not_configured")
        raise HTTPException(
            status_code=503,
            detail="JWT_SECRET is not set in the server .env file.",
        )
    try:
        safe_cid = db_service.sanitize_client_id(body.client_id or "")
    except ValueError as e:
        audit_log.auth_login_failure(
            request,
            role="client",
            reason="invalid_client_id",
            actor=body.client_id,
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    token = auth_service.create_access_token("client", client_id=safe_cid)
    audit_log.auth_login_success(request, role="client", actor=safe_cid)
    return ClientLoginResponse(
        access_token=token,
        token_type="bearer",
        role="client",
        client_id=safe_cid,
    )


@app.get(
    "/catalog/languages",
    tags=["catalog"],
    summary="List catalog languages",
    response_model=LanguagesResponse,
    responses={
        200: {
            "description": "Languages available in the reference catalog.",
            "content": {
                "application/json": {
                    "example": {
                        "languages": [
                            {"id": 1, "code": "python", "name": "Python"},
                            {"id": 2, "code": "javascript", "name": "JavaScript"},
                        ]
                    }
                }
            },
        },
        500: ERROR_500,
    },
)
def public_list_languages() -> LanguagesResponse:
    """
    Public read-only list of programming languages for the participant code editor.

    No authentication required.
    """
    return LanguagesResponse(languages=catalog_service.list_languages())


@app.get(
    "/assessment/{assessment_id}",
    tags=["assessments"],
    summary="Fetch assessment questions",
    response_model=AssessmentResponse,
    responses={
        200: {
            "description": "Assessment metadata and questions (correct answers are never included).",
        },
        **public_assessment_errors(),
    },
)
def get_assessment(
    assessment_id: Annotated[
        str,
        Path(
            description="UUID of the assessment.",
            examples=["550e8400-e29b-41d4-a716-446655440000"],
        ),
    ],
    employee_id: Annotated[
        str | None,
        Query(
            max_length=64,
            description=(
                "Optional participant employee id. When provided, question and MCQ option "
                "order are shuffled deterministically. Required to start a timed attempt."
            ),
            examples=["EMP-10042"],
        ),
    ] = None,
) -> AssessmentResponse:
    """
    Load an assessment for a participant or admin preview.

    **Access**: shared assessments are open; client-scoped assessments return 403 on open routes.

    **Timed assessments**: pass `employee_id` to receive `timer` state and start the clock on first load.
    If the participant already submitted, `already_submitted` is `true` and `questions` is empty.
    """
    try:
        aid = _require_valid_assessment_id(assessment_id)
        if not db_service.client_may_access_assessment(aid, None):
            raise HTTPException(
                status_code=403,
                detail="This assessment is not available for open access.",
            )
        eid = (employee_id or "").strip() or None
        data = assessment_service.get_assessment_for_user(aid, employee_id=eid)
        if not data.get("found"):
            raise HTTPException(status_code=404, detail="Assessment not found")
        return AssessmentResponse.model_validate(data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get(
    "/assessment/{assessment_id}/report",
    tags=["assessments"],
    summary="Participant feedback report",
    responses={
        200: {"description": "Structured feedback for in-browser questions (MCQ + Pyodide)."},
        **public_assessment_errors(),
    },
)
def get_participant_report(
    assessment_id: Annotated[
        str,
        Path(
            description="UUID of the assessment.",
            examples=["550e8400-e29b-41d4-a716-446655440000"],
        ),
    ],
    employee_id: Annotated[
        str,
        Query(
            min_length=1,
            max_length=64,
            description="Participant employee id used when submitting.",
            examples=["EMP-10042"],
        ),
    ],
) -> dict[str, Any]:
    """
    Return a structured feedback report for in-browser questions.

    Jupyter notebook submissions are excluded from v1 reports.
    """
    try:
        aid = _require_valid_assessment_id(assessment_id)
        if not db_service.client_may_access_assessment(aid, None):
            raise HTTPException(
                status_code=403,
                detail="This assessment is not available for open access.",
            )
        return report_service.build_report(aid, employee_id.strip())
    except HTTPException:
        raise
    except ValueError as e:
        msg = str(e)
        status = 404 if "not found" in msg.lower() or "unknown" in msg.lower() else 400
        raise HTTPException(status_code=status, detail=msg) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get(
    "/client/employee-profile",
    tags=["client"],
    summary="Cross-assessment employee performance profile",
    response_model=EmployeeProfileResponse,
    responses={
        200: {"description": "Topic performance rollup for improvement flows."},
        400: ERROR_400,
        500: ERROR_500,
    },
)
def get_client_employee_profile(
    employee_id: Annotated[
        str,
        Query(min_length=1, max_length=64, description="Participant employee id."),
    ],
    scope: Annotated[
        str,
        Query(description="`last_3` for weak areas; `full_history` for new areas / difficulty."),
    ] = "last_3",
    language_code: Annotated[
        str | None,
        Query(max_length=32, description="Optional catalog language code filter."),
    ] = None,
) -> EmployeeProfileResponse:
    """Profile API used by Help me improve (Stage 5+) and report insights."""
    scope_norm = scope.strip().lower()
    if scope_norm not in ("last_3", "full_history"):
        raise HTTPException(
            status_code=400,
            detail="scope must be last_3 or full_history",
        )
    try:
        data = employee_profile_service.get_employee_profile(
            employee_id.strip(),
            language_code=language_code,
            scope=scope_norm,  # type: ignore[arg-type]
        )
        return EmployeeProfileResponse.model_validate(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get(
    "/client/my-report",
    tags=["client"],
    summary="Shippable employee skills progress report",
    response_model=EmployeeReportResponse,
    responses={
        200: {"description": "Full stats report for screen view or PDF export."},
        400: ERROR_400,
        500: ERROR_500,
    },
)
def get_client_employee_report(
    employee_id: Annotated[
        str,
        Query(min_length=1, max_length=64, description="Participant employee id."),
    ],
    period: Annotated[
        str,
        Query(description="`all_time` or `last_90_days`."),
    ] = "all_time",
    language_code: Annotated[
        str | None,
        Query(max_length=32, description="Optional catalog language code filter."),
    ] = None,
) -> EmployeeReportResponse:
    """Participant-facing stats report (self-service when employee_id is known)."""
    period_norm = period.strip().lower()
    if period_norm not in ("all_time", "last_90_days"):
        raise HTTPException(
            status_code=400,
            detail="period must be all_time or last_90_days",
        )
    try:
        data = employee_profile_service.get_employee_report(
            employee_id.strip(),
            language_code=language_code,
            period=period_norm,  # type: ignore[arg-type]
        )
        return EmployeeReportResponse.model_validate(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post(
    "/client/improvement/weak-areas",
    tags=["client"],
    summary="Create bank-only practice assessment on weak topics",
    response_model=WeakAreasImprovementResponse,
    responses={
        200: {"description": "Practice assessment created or availability explanation returned."},
        400: ERROR_400,
        500: ERROR_500,
    },
)
def post_client_improvement_weak_areas(
    body: WeakAreasImprovementRequest,
) -> WeakAreasImprovementResponse:
    """Bank-only weak-areas practice — never calls the LLM."""
    try:
        data = improvement_assessment_service.create_weak_areas_assessment(
            body.employee_id.strip(),
            body.language_code.strip(),
            questions_requested=body.questions_requested,
        )
        return WeakAreasImprovementResponse.model_validate(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post(
    "/client/improvement/new-areas",
    tags=["client"],
    summary="Create bank-only practice assessment on unexplored topics",
    response_model=NewAreasImprovementResponse,
    responses={
        200: {"description": "Practice assessment created or availability explanation returned."},
        400: ERROR_400,
        500: ERROR_500,
    },
)
def post_client_improvement_new_areas(
    body: NewAreasImprovementRequest,
) -> NewAreasImprovementResponse:
    """Bank-only new-areas practice — never calls the LLM."""
    try:
        data = improvement_assessment_service.create_new_areas_assessment(
            body.employee_id.strip(),
            body.language_code.strip(),
            questions_requested=body.questions_requested,
            topics_count=body.topics_count,
        )
        return NewAreasImprovementResponse.model_validate(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post(
    "/client/improvement/difficulty",
    tags=["client"],
    summary="Create bank-only practice assessment at stepped-up difficulty",
    response_model=DifficultyImprovementResponse,
    responses={
        200: {"description": "Practice assessment created or availability explanation returned."},
        400: ERROR_400,
        500: ERROR_500,
    },
)
def post_client_improvement_difficulty(
    body: DifficultyImprovementRequest,
) -> DifficultyImprovementResponse:
    """Bank-only step-up difficulty practice — never calls the LLM."""
    try:
        data = improvement_assessment_service.create_difficulty_improvement_assessment(
            body.employee_id.strip(),
            body.language_code.strip(),
            questions_requested=body.questions_requested,
            topics_count=body.topics_count,
        )
        return DifficultyImprovementResponse.model_validate(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post(
    "/submit-assessment",
    tags=["assessments"],
    summary="Submit in-browser answers",
    response_model=SubmitAssessmentResponse,
    responses={
        200: {"description": "Answers graded and persisted."},
        400: ERROR_400,
        403: {
            "description": "Assessment unavailable, timed window expired, or duplicate submission.",
            "content": {
                "application/json": {
                    "examples": {
                        "expired": {"value": {"detail": "Assessment time has expired."}},
                        "duplicate": {
                            "value": {"detail": "You have already submitted this assessment."}
                        },
                    }
                }
            },
        },
        422: ERROR_422,
        500: ERROR_500,
        503: ERROR_503,
    },
)
def submit_assessment(body: SubmitAssessmentBody) -> SubmitAssessmentResponse:
    """
    Submit participant answers for LLM grading.

    **Access**: shared assessments only on this public route.

    **Validation**: `assessment_id` must be a UUID; at least one answer must match a question.
    Duplicate submissions for the same `employee_id` are rejected with HTTP 400.
    """
    try:
        aid = _require_valid_assessment_id(body.assessment_id)
        if not db_service.client_may_access_assessment(aid, None):
            raise HTTPException(
                status_code=403,
                detail="This assessment is not available for open access.",
            )
        answers_payload = [
            {"question_id": a.question_id, "answer": a.answer} for a in body.answers
        ]
        user_label = f"{body.employee_id} | {body.participant_name}"
        result = assessment_service.submit_assessment(
            assessment_id=aid,
            user_id=user_label,
            answers=answers_payload,
            employee_id=body.employee_id.strip(),
            submitter_client_id=None,
        )
        return SubmitAssessmentResponse.model_validate(result)
    except TimedAssessmentError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post(
    "/submit-notebook-assessment",
    tags=["assessments"],
    summary="Upload Jupyter notebook for grading",
    response_model=NotebookSubmitResponse,
    responses={
        200: {"description": "Notebook parsed, graded, and stored."},
        400: ERROR_400,
        403: {
            "description": "Assessment unavailable or notebook grace period ended.",
            "content": {
                "application/json": {
                    "example": {"detail": "Notebook upload grace period has ended."}
                }
            },
        },
        413: ERROR_413,
        422: ERROR_422,
        500: ERROR_500,
    },
)
async def submit_notebook_assessment(
    assessment_id: Annotated[
        str,
        Form(
            description="UUID of the assessment.",
            examples=["550e8400-e29b-41d4-a716-446655440000"],
        ),
    ],
    user_id: Annotated[
        str,
        Form(
            description="Participant label, typically `employee_id | participant_name`.",
            examples=["EMP-10042 | Jane Doe"],
        ),
    ],
    file: Annotated[
        UploadFile,
        File(description="`.ipynb` notebook file (max 5 MiB)."),
    ],
    client_id: Annotated[
        str | None,
        Header(
            description=(
                "Optional client id for client-scoped assessments. Must match the assessment owner."
            ),
            examples=["participant-1"],
        ),
    ] = None,
) -> NotebookSubmitResponse:
    """
    Upload a completed Jupyter notebook for grading.

    Uses `multipart/form-data` with fields `assessment_id`, `user_id`, and `file`.

    **Access**: shared assessments allow missing `client_id`; client-scoped assessments require
    a matching `client_id` header.

    **Size limit**: 5 MiB (HTTP 413 if exceeded).
    """
    contents = await file.read()
    if len(contents) > MAX_NOTEBOOK_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 5 MiB)")
    try:
        aid = _require_valid_assessment_id(assessment_id)
        if not db_service.client_may_access_assessment(aid, client_id):
            raise HTTPException(
                status_code=403,
                detail="This assessment is not available for open access.",
            )
        result = notebook_service.submit_notebook_assessment(
            aid, user_id, contents, submitter_client_id=client_id
        )
        return NotebookSubmitResponse.model_validate(result)
    except TimedAssessmentError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get(
    "/assessment/{assessment_id}/template",
    tags=["assessments"],
    summary="Download Jupyter notebook template",
    responses={
        200: {
            "description": "Notebook template (`.ipynb` JSON).",
            "content": {
                "application/x-ipynb+json": {
                    "schema": {"type": "object"},
                    "example": {
                        "nbformat": 4,
                        "nbformat_minor": 2,
                        "metadata": {"language_info": {"name": "python"}},
                        "cells": [],
                    },
                }
            },
        },
        400: ERROR_400,
        403: {
            "description": "Client-scoped assessment without matching `client_id` header.",
            "content": {
                "application/json": {"example": {"detail": "This assessment is not available for open access."}}
            },
        },
        404: {
            "description": "Assessment not found or does not require a notebook.",
            "content": {
                "application/json": {
                    "examples": {
                        "not_found": {"value": {"detail": "Assessment not found"}},
                        "no_notebook": {
                            "value": {"detail": "This assessment does not require a Jupyter notebook."}
                        },
                    }
                }
            },
        },
        409: {
            "description": "Notebook expected but template is not ready.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": (
                            "This assessment expects notebook coding questions, but none are "
                            "available in the template. Regenerate the assessment."
                        )
                    }
                }
            },
        },
        500: ERROR_500,
    },
)
def get_notebook_template(
    assessment_id: Annotated[
        str,
        Path(
            description="UUID of the assessment.",
            examples=["550e8400-e29b-41d4-a716-446655440000"],
        ),
    ],
    client_id: Annotated[
        str | None,
        Header(
            description="Optional client id for client-scoped assessments.",
            examples=["participant-1"],
        ),
    ] = None,
) -> Response:
    """
    Download a starter `.ipynb` with markdown prompts for notebook coding questions.

    Returns raw notebook JSON with `Content-Disposition: attachment`.

    **Authentication**: none for shared assessments; `client_id` header when scoped.
    """
    try:
        aid = _require_valid_assessment_id(assessment_id)
        if not db_service.client_may_access_assessment(aid, client_id):
            raise HTTPException(
                status_code=403,
                detail="This assessment is not available for open access.",
            )
        rows = db_service.read_questions_by_assessment(aid)
        if not rows:
            raise HTTPException(status_code=404, detail="Assessment not found")

        from services.notebook_plan_service import notebook_plan_for_assessment

        plan = notebook_plan_for_assessment(aid)
        if not plan["notebook_expected"]:
            raise HTTPException(
                status_code=404,
                detail="This assessment does not require a Jupyter notebook.",
            )
        if not plan["notebook_ready"]:
            raise HTTPException(
                status_code=409,
                detail=(
                    "This assessment expects notebook coding questions, but none are "
                    "available in the template. Regenerate the assessment."
                ),
            )

        notebook_questions = assessment_service.get_notebook_template_questions(aid)
        nb_dict = assessment_service.build_notebook_template(notebook_questions, aid)
        nb_json = json.dumps(nb_dict, indent=1)
        return Response(
            content=nb_json,
            media_type="application/x-ipynb+json",
            headers={"Content-Disposition": f"attachment; filename=assessment_{aid}.ipynb"},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
