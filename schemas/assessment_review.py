"""Admin assessment review / re-review API schemas (Stage 13)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from schemas.admin import ReviewQuestionItem

ReviewStatus = Literal["draft", "in_review", "published"]


class ReviewAssessmentMetadata(BaseModel):
    topic: str = Field(default="Assessment", min_length=1)
    level: str = Field(..., min_length=1)
    language_code: str | None = Field(default=None, max_length=32)
    language_label: str | None = Field(default=None, max_length=256)
    topic_names: list[str] = Field(default_factory=list)
    per_topic_config: dict[str, dict[str, int]] = Field(default_factory=dict)
    is_timed: bool = False
    duration_minutes: int | None = Field(default=None, ge=1)
    notebook_grace_minutes: int | None = Field(default=None, ge=0)
    allow_pyodide_paste: bool = False
    certificate_enabled: bool = False
    question_source: str = "generate_new"
    include_sample_test_cases: bool = False
    include_beginner_coding_hints: bool = False
    generation_provider: str = "grok"
    alias: str | None = Field(default=None, max_length=120)

    @field_validator("topic", mode="before")
    @classmethod
    def normalize_topic(cls, v: str | None) -> str:
        s = (v or "").strip() if v is not None else ""
        return s or "Assessment"

    @field_validator("level")
    @classmethod
    def normalize_level(cls, v: str) -> str:
        lv = v.strip().lower()
        if lv not in ("beginner", "intermediate", "advanced"):
            raise ValueError("level must be beginner, intermediate, or advanced")
        return lv

    @field_validator("alias", mode="before")
    @classmethod
    def strip_alias(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s or None


class DraftAssessmentBody(ReviewAssessmentMetadata):
    """Create a draft assessment shell for incremental review saves."""


class DraftAssessmentResponse(BaseModel):
    assessment_id: str
    review_status: ReviewStatus = "draft"


class ReviewQuestionItemExtended(ReviewQuestionItem):
    saved_at: str | None = None
    is_dirty: bool = False


class ReviewBundleResponse(BaseModel):
    assessment_id: str
    review_status: ReviewStatus
    alias: str | None = None
    topic: str = ""
    level: str = ""
    language_code: str | None = None
    language_label: str | None = None
    topic_names: list[str] = Field(default_factory=list)
    per_topic_config: dict[str, dict[str, int]] = Field(default_factory=dict)
    is_timed: bool = False
    duration_minutes: int | None = None
    notebook_grace_minutes: int | None = None
    allow_pyodide_paste: bool = False
    certificate_enabled: bool = False
    question_source: str = "generate_new"
    include_sample_test_cases: bool = False
    include_beginner_coding_hints: bool = False
    generation_provider: str = "grok"
    questions: list[ReviewQuestionItemExtended] = Field(default_factory=list)
    saved_count: int = 0
    question_count: int = 0


class SaveReviewQuestionResponse(BaseModel):
    ok: bool = True
    assessment_id: str
    question_id: str
    bank_question_id: int | None = None
    saved_at: str
    revised: bool = False


class PublishReviewBody(BaseModel):
    questions: list[ReviewQuestionItem] = Field(..., min_length=1)
    metadata: ReviewAssessmentMetadata | None = None


class PublishReviewResponse(BaseModel):
    assessment_id: str
    review_status: ReviewStatus = "published"
    question_count: int


class RegenerateReviewQuestionBody(BaseModel):
    level: str
    language_code: str | None = None
    topic_name: str = ""
    question_type: str
    reference_question: ReviewQuestionItem
    admin_preference: str | None = Field(default=None, max_length=2000)
    include_sample_test_cases: bool = False
    include_beginner_coding_hints: bool = False
    generation_provider: str = "grok"

    @field_validator("level")
    @classmethod
    def normalize_level(cls, v: str) -> str:
        lv = v.strip().lower()
        if lv not in ("beginner", "intermediate", "advanced"):
            raise ValueError("level must be beginner, intermediate, or advanced")
        return lv

    @field_validator("question_type")
    @classmethod
    def normalize_type(cls, v: str) -> str:
        t = v.strip().lower()
        if t not in ("mcq", "coding", "subjective"):
            raise ValueError("question_type must be mcq, coding, or subjective")
        return t


class PatchAssessmentAliasBody(BaseModel):
    alias: str | None = Field(default=None, max_length=120)

    @field_validator("alias", mode="before")
    @classmethod
    def strip_alias(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s or None
