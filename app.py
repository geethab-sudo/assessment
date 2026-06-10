"""
FastAPI application: AI assessment generation, retrieval, and graded submission.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal

from dotenv import load_dotenv

# Load `.env` next to this file first so GROQ_API_KEY is set even if the shell cwd differs.
_root = Path(__file__).resolve().parent
load_dotenv(_root / ".env", override=True)
load_dotenv(override=True)

from fastapi import Depends, FastAPI, HTTPException, Query, Form, File, UploadFile, Header, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator, model_validator

import json
import uuid

from services import assessment_service, auth_service, catalog_service, notebook_service, report_service
from services import db_service
from services.attempt_service import TimedAssessmentError
from services.database import init_db, ping_database
from services.llm_service import groq_key_configured

ALLOWED_TYPES = frozenset({"mcq", "coding", "subjective"})
MAX_NOTEBOOK_BYTES = 5 * 1024 * 1024  # 5 MiB


def _require_valid_assessment_id(raw: str) -> str:
    """Strip and validate that the path param is a well-formed UUID. Raises HTTPException."""
    aid = raw.strip()
    try:
        uuid.UUID(aid)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid assessment ID format") from None
    return aid


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="AI Assessment API", version="1.0.0", lifespan=lifespan)

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

security = HTTPBearer(auto_error=False)


def get_bearer_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Not authenticated")
    return credentials.credentials


def require_admin(_token: Annotated[str, Depends(get_bearer_token)]) -> None:
    try:
        role = auth_service.decode_token_get_role(_token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from None
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")


class LoginBody(BaseModel):
    role: Literal["admin", "client"]
    password: str | None = None
    client_id: str | None = None

    @model_validator(mode="after")
    def validate_login_fields(self) -> LoginBody:
        if self.role == "admin":
            if not (self.password or "").strip():
                raise ValueError("password is required for admin login")
        else:
            if not (self.client_id or "").strip():
                raise ValueError("client_id is required for client login")
        return self


class GenerateAssessmentBody(BaseModel):
    topic: str = Field(..., min_length=1)
    level: str = Field(..., min_length=1)
    types: list[str] = Field(..., min_length=1)
    questions_per_type: dict[str, int] = Field(
        ...,
        description="Count per question type; keys must match types (e.g. mcq: 2, coding: 1).",
    )
    #: Optional catalog `languages.code` for code-editor mode on coding questions (e.g. py, js)
    language_code: str | None = Field(default=None, max_length=32)
    #: Catalog language name for admin list (not the syntax code); code is stored separately.
    language_label: str | None = Field(default=None, max_length=256)
    #: Selected catalog topic titles (or custom topic preview), in order
    topic_names: list[str] = Field(default_factory=list)
    #: Per-topic question counts: { "Topic name": { "mcq": 1, "coding": 1, "subjective": 0 } }
    per_topic_config: dict[str, dict[str, int]] = Field(default_factory=dict)
    is_timed: bool = False
    duration_minutes: int | None = Field(default=None, ge=1)
    notebook_grace_minutes: int | None = Field(default=None, ge=0)

    @field_validator("topic", mode="before")
    @classmethod
    def strip_topic(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("language_code", mode="before")
    @classmethod
    def strip_language_code(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if isinstance(v, str) and (s := v.strip()):
            return s[:32]
        return None

    @field_validator("language_label", mode="before")
    @classmethod
    def strip_language_label(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if isinstance(v, str) and (s := v.strip()):
            return s[:256]
        return None

    @field_validator("topic_names", mode="before")
    @classmethod
    def normalize_topic_names(cls, v: object) -> list[str]:
        if v is None:
            return []
        if not isinstance(v, list):
            raise ValueError("topic_names must be a list of strings")
        out: list[str] = []
        for item in v[:50]:
            s = str(item).strip()
            if s:
                out.append(s[:512])
        return out

    @field_validator("level")
    @classmethod
    def normalize_level(cls, v: str) -> str:
        lv = v.strip().lower()
        if lv not in ("beginner", "intermediate", "advanced"):
            raise ValueError("level must be one of: beginner, intermediate, advanced")
        return lv

    @field_validator("types")
    @classmethod
    def normalize_types(cls, v: list[str]) -> list[str]:
        out = list(
            dict.fromkeys(t.strip().lower() for t in v if t.strip())
        )
        bad = [t for t in out if t not in ALLOWED_TYPES]
        if bad:
            raise ValueError(
                f"Invalid question types: {bad}. Allowed: mcq, coding, subjective"
            )
        if not out:
            raise ValueError("Provide at least one valid question type")
        return out

    @field_validator("questions_per_type", mode="before")
    @classmethod
    def normalize_questions_per_type(
        cls, v: object
    ) -> dict[str, int]:
        if not isinstance(v, dict) or not v:
            raise ValueError(
                "questions_per_type must be a non-empty object, e.g. "
                '{"mcq": 2, "coding": 1}'
            )
        out: dict[str, int] = {}
        for k, n in v.items():
            if not str(k).strip():
                continue
            key = str(k).strip().lower()
            try:
                out[key] = int(n)
            except (TypeError, ValueError) as e:
                raise ValueError(f"Invalid count for {k!r}") from e
        if not out:
            raise ValueError("questions_per_type must include at least one type")
        return out

    @model_validator(mode="after")
    def match_types_and_counts(self) -> GenerateAssessmentBody:
        st = set(self.types)
        sk = set(self.questions_per_type.keys())
        if st != sk:
            raise ValueError(
                "questions_per_type keys must match the types list exactly: "
                f"types={sorted(st)}, got keys={sorted(sk)}"
            )
        for t, n in self.questions_per_type.items():
            if n < 1 or n > 30:
                raise ValueError(f"Count for {t} must be between 1 and 30 (got {n})")
        if self.is_timed and self.duration_minutes is None:
            raise ValueError("duration_minutes is required when is_timed is true")
        if not self.is_timed:
            object.__setattr__(self, "duration_minutes", None)
            object.__setattr__(self, "notebook_grace_minutes", None)
        return self


class ReviewQuestionItem(BaseModel):
    """One question as returned by preview and submitted back via confirm."""
    question_id: str
    type: str
    question: str = Field(..., min_length=1)
    code_snippet: str = ""
    options: list[str] = Field(default_factory=list)
    correct_answer: str = ""
    topic_name: str = ""

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        t = v.strip().lower()
        if t not in ALLOWED_TYPES:
            raise ValueError(f"Invalid question type: {v!r}")
        return t

    @field_validator("question", "code_snippet", "correct_answer", "topic_name", mode="before")
    @classmethod
    def strip_str(cls, v: object) -> str:
        return v.strip() if isinstance(v, str) else (v or "")


class ConfirmAssessmentBody(BaseModel):
    questions: list[ReviewQuestionItem] = Field(..., min_length=1)
    topic: str = Field(..., min_length=1)
    level: str = Field(..., min_length=1)
    language_code: str | None = Field(default=None, max_length=32)
    language_label: str | None = Field(default=None, max_length=256)
    topic_names: list[str] = Field(default_factory=list)
    per_topic_config: dict[str, dict[str, int]] = Field(default_factory=dict)
    is_timed: bool = False
    duration_minutes: int | None = Field(default=None, ge=1)
    notebook_grace_minutes: int | None = Field(default=None, ge=0)

    @field_validator("level")
    @classmethod
    def normalize_level(cls, v: str) -> str:
        lv = v.strip().lower()
        if lv not in ("beginner", "intermediate", "advanced"):
            raise ValueError("level must be one of: beginner, intermediate, advanced")
        return lv


class PatchQuestionBody(BaseModel):
    question: str | None = None
    code_snippet: str | None = None
    options: list[str] | None = None
    correct_answer: str | None = None

    @field_validator("question", "code_snippet", "correct_answer", mode="before")
    @classmethod
    def strip_str(cls, v: object) -> str | None:
        if v is None:
            return None
        return v.strip() if isinstance(v, str) else str(v)


class AnswerItem(BaseModel):
    question_id: str | int
    answer: str


class SubmitAssessmentBody(BaseModel):
    assessment_id: str
    employee_id: str = Field(..., min_length=1, max_length=64)
    participant_name: str = Field(..., min_length=1, max_length=256)
    answers: list[AnswerItem]

    @field_validator("assessment_id", "employee_id", "participant_name", mode="before")
    @classmethod
    def strip_participant_fields(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip()
        return v


class RelatedDocumentItem(BaseModel):
    """One reference (title required; at least one of url or path is typical)."""

    title: str = Field(..., min_length=1, max_length=512)
    url: str | None = Field(default=None, max_length=2048)
    path: str | None = Field(default=None, max_length=2048)


class LanguageCreateBody(BaseModel):
    code: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=128)

    @field_validator("code", "name", mode="before")
    @classmethod
    def strip_s(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip()
        return v


class TopicCreateBody(BaseModel):
    language_id: int = Field(..., ge=1, description="FK to languages.id")
    name: str = Field(..., min_length=1, max_length=256)
    related_documents: list[RelatedDocumentItem] = Field(
        default_factory=list,
        description="Related docs as JSON objects (stored in JSONB).",
    )

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


@app.post("/auth/login")
def login(body: LoginBody) -> dict[str, str]:
    if body.role == "admin":
        if not auth_service.admin_password_configured():
            raise HTTPException(
                status_code=503,
                detail="Admin login is not configured. Set ADMIN_PASSWORD in the server .env file.",
            )
        if not auth_service.verify_admin_password(body.password or ""):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        token = auth_service.create_access_token("admin")
        return {"access_token": token, "token_type": "bearer", "role": "admin"}

    if not auth_service.jwt_configured():
        raise HTTPException(
            status_code=503,
            detail="JWT_SECRET is not set in the server .env file.",
        )
    try:
        safe_cid = db_service.sanitize_client_id(body.client_id or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    token = auth_service.create_access_token("client", client_id=safe_cid)
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": "client",
        "client_id": safe_cid,
    }


@app.get("/admin/assessments")
def admin_list_assessments(_: None = Depends(require_admin)) -> dict[str, Any]:
    return {"assessments": db_service.list_assessments_summary()}


@app.get("/admin/assessment/{assessment_id}")
def admin_get_assessment_preview(
    assessment_id: str, _: None = Depends(require_admin)
) -> dict[str, Any]:
    """Admin: load questions for preview (same shape as the participant view; no correct answers)."""
    aid = assessment_id.strip()
    data = assessment_service.get_assessment_for_user(aid)
    if not data.get("found"):
        raise HTTPException(status_code=404, detail="Assessment not found")
    return data


@app.delete("/admin/assessments/{assessment_id}")
def admin_delete_assessment(
    assessment_id: str, _: None = Depends(require_admin)
) -> dict[str, Any]:
    aid = assessment_id.strip()
    if not aid:
        raise HTTPException(status_code=400, detail="Assessment ID is required")
    try:
        db_service.delete_assessment(aid)
    except ValueError as e:
        msg = str(e)
        status = 404 if msg == "Assessment not found" else 400
        raise HTTPException(status_code=status, detail=msg) from e
    return {"ok": True, "deleted": aid}


@app.get("/admin/submissions")
def admin_list_submissions(_: None = Depends(require_admin)) -> dict[str, Any]:
    return {"submissions": db_service.list_all_submissions()}


@app.get("/admin/languages")
def admin_list_languages(_: None = Depends(require_admin)) -> dict[str, Any]:
    return {"languages": catalog_service.list_languages()}


@app.post("/admin/languages")
def admin_create_language(
    body: LanguageCreateBody, _: None = Depends(require_admin)
) -> dict[str, Any]:
    try:
        return {"language": catalog_service.create_language(code=body.code, name=body.name)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.put("/admin/languages/{language_id}")
def admin_update_language(
    language_id: int, body: LanguageCreateBody, _: None = Depends(require_admin)
) -> dict[str, Any]:
    try:
        return {
            "language": catalog_service.update_language(
                language_id=language_id, code=body.code, name=body.name
            )
        }
    except ValueError as e:
        msg = str(e)
        status = 404 if msg == "Language not found" else 400
        raise HTTPException(status_code=status, detail=msg) from e


@app.get("/admin/topics")
def admin_list_topics(
    language_id: Annotated[int | None, Query()] = None,
    _: None = Depends(require_admin),
) -> dict[str, Any]:
    return {"topics": catalog_service.list_topics(language_id=language_id)}


@app.post("/admin/topics")
def admin_create_topic(
    body: TopicCreateBody, _: None = Depends(require_admin)
) -> dict[str, Any]:
    try:
        docs = [d.model_dump(exclude_none=True) for d in body.related_documents]
        return {
            "topic": catalog_service.create_topic(
                language_id=body.language_id,
                name=body.name,
                related_documents=docs,
            )
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.put("/admin/topics/{topic_id}")
def admin_update_topic(
    topic_id: int, body: TopicCreateBody, _: None = Depends(require_admin)
) -> dict[str, Any]:
    try:
        docs = [d.model_dump(exclude_none=True) for d in body.related_documents]
        return {
            "topic": catalog_service.update_topic(
                topic_id=topic_id,
                language_id=body.language_id,
                name=body.name,
                related_documents=docs,
            )
        }
    except ValueError as e:
        msg = str(e)
        status = 404 if msg == "Topic not found" else 400
        raise HTTPException(status_code=status, detail=msg) from e


@app.delete("/admin/topics/{topic_id}")
def admin_delete_topic(
    topic_id: int, _: None = Depends(require_admin)
) -> dict[str, Any]:
    try:
        catalog_service.delete_topic(topic_id=topic_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"ok": True, "deleted": topic_id}


@app.post("/generate-assessment")
def generate_assessment(
    body: GenerateAssessmentBody,
    _: None = Depends(require_admin),
) -> dict[str, Any]:
    """Admin: generate questions via LLM and persist to PostgreSQL."""
    try:
        return assessment_service.create_assessment(
            topic=body.topic.strip(),
            level=body.level,
            types=body.types,  # already normalized by Pydantic validator
            questions_per_type=body.questions_per_type,
            language_code=body.language_code,
            language_label=body.language_label,
            topic_names=body.topic_names,
            per_topic_config=body.per_topic_config or {},
            is_timed=body.is_timed,
            duration_minutes=body.duration_minutes,
            notebook_grace_minutes=body.notebook_grace_minutes,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {e}") from e


@app.post("/admin/preview-questions")
def preview_questions(
    body: GenerateAssessmentBody,
    _: None = Depends(require_admin),
) -> dict[str, Any]:
    """Admin: generate questions via LLM for review — nothing is written to the DB.

    Returns the full question list including correct_answer so the admin can verify
    and edit before confirming. Call POST /admin/confirm-assessment to persist.
    """
    try:
        return assessment_service.preview_questions(
            topic=body.topic.strip(),
            level=body.level,
            types=body.types,
            questions_per_type=body.questions_per_type,
            topic_names=body.topic_names,
            per_topic_config=body.per_topic_config or {},
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Preview generation failed: {e}") from e


@app.post("/admin/confirm-assessment")
def confirm_assessment(
    body: ConfirmAssessmentBody,
    _: None = Depends(require_admin),
) -> dict[str, Any]:
    """Admin: persist the reviewed (and possibly edited) question list to the DB."""
    try:
        questions = [q.model_dump() for q in body.questions]
        return assessment_service.confirm_assessment(
            questions,
            topic=body.topic.strip(),
            level=body.level,
            language_code=body.language_code,
            language_label=body.language_label,
            topic_names=body.topic_names,
            per_topic_config=body.per_topic_config or {},
            is_timed=body.is_timed,
            duration_minutes=body.duration_minutes,
            notebook_grace_minutes=body.notebook_grace_minutes,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Confirm failed: {e}") from e


@app.patch("/admin/assessment/{assessment_id}/question/{question_id}")
def patch_assessment_question(
    assessment_id: str,
    question_id: str,
    body: PatchQuestionBody,
    _: None = Depends(require_admin),
) -> dict[str, Any]:
    """Admin: update a single question on an already-saved assessment (post-hoc correction)."""
    aid = _require_valid_assessment_id(assessment_id)
    options_str: str | None = None
    if body.options is not None:
        options_str = json.dumps(body.options, ensure_ascii=False)
    updated = db_service.update_assessment_question(
        aid,
        question_id.strip(),
        question=body.question,
        code_snippet=body.code_snippet,
        options=options_str,
        correct_answer=body.correct_answer,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Question not found")
    return {"ok": True, "assessment_id": aid, "question_id": question_id.strip()}


@app.get("/catalog/languages")
def public_list_languages() -> dict[str, Any]:
    """Public: language codes and names for participant code editor (read-only)."""
    return {"languages": catalog_service.list_languages()}


@app.get("/assessment/{assessment_id}")
def get_assessment(
    assessment_id: str,
    employee_id: str | None = Query(default=None, max_length=64),
) -> dict[str, Any]:
    """Public: fetch questions (no correct answers). Pass employee_id for per-participant shuffle."""
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
        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/assessment/{assessment_id}/report")
def get_participant_report(
    assessment_id: str,
    employee_id: Annotated[str, Query(min_length=1, max_length=64)],
) -> dict[str, Any]:
    """Public: feedback report for in-browser questions (MCQ + Pyodide coding). Jupyter excluded."""
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


@app.post("/submit-assessment")
def submit_assessment(body: SubmitAssessmentBody) -> dict[str, Any]:
    """Public: submit answers; LLM evaluates; participant identified by employee_id + name."""
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
        return assessment_service.submit_assessment(
            assessment_id=aid,
            user_id=user_label,
            answers=answers_payload,
            employee_id=body.employee_id.strip(),
            submitter_client_id=None,
        )
    except TimedAssessmentError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/submit-notebook-assessment")
async def submit_notebook_assessment(
    assessment_id: str = Form(...),
    user_id: str = Form(...),
    file: UploadFile = File(...),
    client_id: str | None = Header(None),
):
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
        return result
    except TimedAssessmentError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/assessment/{assessment_id}/template")
def get_notebook_template(assessment_id: str, client_id: str | None = Header(None)):
    """Public: download Jupyter notebook template for coding questions."""
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


@app.get("/health")
def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "database": ping_database(),
        "groq_configured": groq_key_configured(),
        "auth_configured": bool(
            auth_service.jwt_configured() and auth_service.admin_password_configured()
        ),
    }
