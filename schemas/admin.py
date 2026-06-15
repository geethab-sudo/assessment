"""Pydantic request and response models for admin API routes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ALLOWED_TYPES = frozenset({"mcq", "coding", "subjective"})


class GenerateAssessmentBody(BaseModel):
    """Request body for LLM-powered assessment generation."""

    topic: str = Field(
        ...,
        min_length=1,
        description="Primary topic label passed to the LLM (legacy single-topic mode).",
        examples=["Python data structures"],
    )
    level: str = Field(
        ...,
        min_length=1,
        description="Difficulty tier: `beginner`, `intermediate`, or `advanced`.",
        examples=["beginner"],
    )
    types: list[str] = Field(
        ...,
        min_length=1,
        description="Question types to generate. Allowed: `mcq`, `coding`, `subjective`.",
        examples=[["mcq", "coding"]],
    )
    questions_per_type: dict[str, int] = Field(
        ...,
        description="Count per question type; keys must match types (e.g. mcq: 2, coding: 1).",
    )
    language_code: str | None = Field(default=None, max_length=32)
    language_label: str | None = Field(default=None, max_length=256)
    topic_names: list[str] = Field(default_factory=list)
    per_topic_config: dict[str, dict[str, int]] = Field(default_factory=dict)
    is_timed: bool = Field(
        False,
        description="When `true`, participants get a timed attempt window.",
    )
    duration_minutes: int | None = Field(
        default=None,
        ge=1,
        description="Main timer length in minutes (required when `is_timed` is `true`).",
    )
    notebook_grace_minutes: int | None = Field(
        default=None,
        ge=0,
        description="Extra minutes after main timer for notebook upload (timed assessments only).",
    )
    question_source: Literal["generate_new", "recycle_then_generate"] = Field(
        default="generate_new",
        description="`recycle_then_generate` pulls from the bank first, then LLM for any shortfall.",
    )
    target_employee_id: str | None = Field(
        default=None,
        max_length=64,
        description="When recycling, exclude bank questions this employee has already mastered.",
    )

    @field_validator("target_employee_id", mode="before")
    @classmethod
    def strip_target_employee_id(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if isinstance(v, str) and (s := v.strip()):
            return s[:64]
        return None

    @field_validator("question_source")
    @classmethod
    def normalize_question_source(cls, v: str) -> str:
        qs = v.strip().lower()
        if qs not in ("generate_new", "recycle_then_generate"):
            raise ValueError(
                "question_source must be generate_new or recycle_then_generate"
            )
        return qs

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
        out = list(dict.fromkeys(t.strip().lower() for t in v if t.strip()))
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
    def normalize_questions_per_type(cls, v: object) -> dict[str, int]:
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

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "topic": "Python",
                    "level": "beginner",
                    "types": ["mcq", "coding"],
                    "questions_per_type": {"mcq": 2, "coding": 1},
                    "language_code": "python",
                    "language_label": "Python",
                    "topic_names": ["Python Basics"],
                    "is_timed": False,
                },
                {
                    "topic": "Python",
                    "level": "intermediate",
                    "types": ["mcq"],
                    "questions_per_type": {"mcq": 5},
                    "is_timed": True,
                    "duration_minutes": 45,
                    "notebook_grace_minutes": 10,
                },
            ]
        }
    )


class GenerateAssessmentResponse(BaseModel):
    """Assessment created and persisted after LLM generation."""

    assessment_id: str
    topic: str
    level: str
    difficulty: str = Field(..., description="Internal LLM difficulty label.")
    types: list[str]
    questions_per_type: dict[str, int]
    question_count: int
    language_code: str | None = None
    language_label: str | None = None
    topic_names: list[str] = Field(default_factory=list)
    notebook_expected: bool = False
    notebook_ready: bool = False
    expected_notebook_coding_count: int = 0
    actual_notebook_coding_count: int = 0
    is_timed: bool = False
    duration_minutes: int | None = None
    notebook_grace_minutes: int | None = None
    bank_sourced_count: int = 0
    llm_generated_count: int = 0
    shortage_messages: list[str] = Field(default_factory=list)

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "assessment_id": "550e8400-e29b-41d4-a716-446655440000",
                    "topic": "Python",
                    "level": "beginner",
                    "difficulty": "easy",
                    "types": ["mcq", "coding"],
                    "questions_per_type": {"mcq": 2, "coding": 1},
                    "question_count": 3,
                    "language_code": "python",
                    "language_label": "Python",
                    "topic_names": ["Python Basics"],
                    "notebook_expected": False,
                    "notebook_ready": False,
                    "expected_notebook_coding_count": 0,
                    "actual_notebook_coding_count": 0,
                    "is_timed": False,
                    "duration_minutes": None,
                    "notebook_grace_minutes": None,
                }
            ]
        }
    )


class AssessmentSummary(BaseModel):
    """Summary row for the admin assessments list."""

    assessment_id: str
    client_id: str = Field(..., description="Owner client id, or `common` for shared assessments.")
    question_count: int
    source: Literal["shared", "client"]
    language_code: str | None = None
    language_label: str | None = None
    language_name: str | None = None
    topic_names: list[str] = Field(default_factory=list)
    created_at: str | None = None
    routing_flag: str | None = None
    is_timed: bool = False
    duration_minutes: int | None = None
    notebook_grace_minutes: int | None = None


class AssessmentsListResponse(BaseModel):
    """All assessments visible to the admin."""

    assessments: list[AssessmentSummary]

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "assessments": [
                        {
                            "assessment_id": "550e8400-e29b-41d4-a716-446655440000",
                            "client_id": "common",
                            "question_count": 5,
                            "source": "shared",
                            "language_code": "python",
                            "language_label": "Python",
                            "language_name": "Python",
                            "topic_names": ["Python Basics"],
                            "created_at": "2025-06-01T12:00:00+00:00",
                            "routing_flag": "pyodide",
                            "is_timed": False,
                            "duration_minutes": None,
                            "notebook_grace_minutes": None,
                        }
                    ]
                }
            ]
        }
    )


class SubmissionRow(BaseModel):
    """A single graded answer stored in the submissions table."""

    assessment_id: str
    user_id: str
    question_id: str
    user_answer: str
    score: str
    feedback: str
    timestamp: str
    client_id: str
    routing_flag: str | None = None


class SubmissionsListResponse(BaseModel):
    """All submission rows across assessments."""

    submissions: list[SubmissionRow]

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "submissions": [
                        {
                            "assessment_id": "550e8400-e29b-41d4-a716-446655440000",
                            "user_id": "EMP-10042 | Jane Doe",
                            "question_id": "1",
                            "user_answer": "def add(a,b): return a+b",
                            "score": "0.9",
                            "feedback": "Good solution.",
                            "timestamp": "2025-06-01T14:30:00+00:00",
                            "client_id": "common",
                            "routing_flag": "pyodide",
                        }
                    ]
                }
            ]
        }
    )


class RelatedDocumentItem(BaseModel):
    title: str = Field(..., min_length=1, max_length=512)
    url: str | None = Field(default=None, max_length=2048)
    path: str | None = Field(default=None, max_length=2048)


class LanguageCreateBody(BaseModel):
    """Create or update a catalog language."""

    code: str = Field(
        ...,
        min_length=1,
        max_length=32,
        description="Unique language code.",
        examples=["python"],
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Human-readable language name.",
        examples=["Python"],
    )

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"code": "python", "name": "Python"}]}
    )

    @field_validator("code", "name", mode="before")
    @classmethod
    def strip_s(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip()
        return v


class ReviewQuestionItem(BaseModel):
    """One question as returned by preview and submitted back via confirm."""

    question_id: str
    type: str
    question: str = Field(..., min_length=1)
    code_snippet: str = ""
    options: list[str] = Field(default_factory=list)
    correct_answer: str = ""
    topic_name: str = ""
    bank_question_id: int | None = None

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


class TopicCreateBody(BaseModel):
    """Create or update a catalog topic."""

    language_id: int = Field(..., ge=1, description="Foreign key to `languages.id`.")
    name: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Topic display name (unique per language).",
        examples=["Python Basics"],
    )
    related_documents: list[RelatedDocumentItem] = Field(
        default_factory=list,
        description="Optional reference documents stored as JSONB.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "language_id": 1,
                    "name": "Python Basics",
                    "related_documents": [
                        {"title": "Official docs", "url": "https://docs.python.org"}
                    ],
                }
            ]
        }
    )

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


class QuestionBankItem(BaseModel):
    id: int
    question_text: str
    type: str
    topic_name: str
    language_code: str
    difficulty: str
    created_at: str
    times_used: int
    times_correct: int
    times_wrong: int
    percent_correct: float
    percent_wrong: float


class QuestionBankListResponse(BaseModel):
    questions: list[QuestionBankItem]


class TopicAvailability(BaseModel):
    topic_name: str
    available: int


class BankAvailabilityResponse(BaseModel):
    available: int
    requested: int
    shortage: int
    per_topic: list[TopicAvailability]

