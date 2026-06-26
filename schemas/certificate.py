"""Certificate generation API schemas (Stage 10)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CertificateOffer(BaseModel):
    """Shown after submit when the participant may claim a certificate."""

    level: str = Field(..., description="beginner | intermediate | advanced")
    language_label: str = Field(..., examples=["Python"])
    threshold_percent: int = Field(85, description="Minimum average score percent to qualify.")


class ClientGenerateCertificateBody(BaseModel):
    assessment_id: str = Field(..., min_length=1)
    employee_id: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=256)

    @field_validator("assessment_id", "employee_id", "display_name", mode="before")
    @classmethod
    def strip_fields(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip()
        return v


class AdminIssueCertificateBody(BaseModel):
    employee_id: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=256)
    level: str = Field(..., min_length=1)
    assessment_id: str | None = Field(default=None, max_length=36)
    language_code: str | None = Field(default=None, max_length=32)
    language_label: str | None = Field(default=None, max_length=256)

    @field_validator("employee_id", "display_name", "assessment_id", mode="before")
    @classmethod
    def strip_optional(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            return v.strip() or None
        return v

    @field_validator("language_code", "language_label", mode="before")
    @classmethod
    def strip_language_fields(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s or None
        return v

    @field_validator("level")
    @classmethod
    def normalize_level(cls, v: str) -> str:
        lv = v.strip().lower()
        if lv not in ("beginner", "intermediate", "advanced"):
            raise ValueError("level must be beginner, intermediate, or advanced")
        return lv


class CertificateIssuedResponse(BaseModel):
    issued_id: int
    filename: str
    level: str
    display_name: str
    language_code: str | None = None
    language_label: str | None = None


class CertificateShareMetadataResponse(BaseModel):
    certificate_id: int
    title: str
    display_name: str
    level: str
    issued_at: str | None = None
    issue_year: int | None = None
    issue_month: int | None = None
    organization_name: str
    verification_url: str
    share_url: str
    image_url: str
    linkedin_url: str
    skills: list[str] = Field(default_factory=list)
    media_title: str
    media_description: str


class CertificateIssuerSettingsBody(BaseModel):
    organization_name: str = Field(..., min_length=1, max_length=256)
    verification_intro: str = Field(..., min_length=1, max_length=2000)

    @field_validator("organization_name", "verification_intro", mode="before")
    @classmethod
    def strip_fields(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip()
        return v


class CertificateIssuerSettingsResponse(BaseModel):
    organization_name: str
    verification_intro: str


class PublicCertificateSettingsResponse(BaseModel):
    organization_name: str
    verification_intro: str


class CertificateVerificationResponse(BaseModel):
    """Public credential verification (Coursera-style)."""

    certificate_id: int
    verified: bool = True
    display_name: str
    title: str
    level: str
    language_label: str
    organization_name: str
    issued_at: str | None = None
    issue_year: int | None = None
    issue_month: int | None = None
    score_percent: int | None = None
    verification_url: str
    image_url: str
    skills: list[str] = Field(default_factory=list)
    media_title: str
    media_description: str
    verification_intro: str
    verification_description: str


class CertificateEarnedItem(BaseModel):
    """One certificate row earned by an employee."""

    id: int
    display_name: str
    level: str
    language_code: str | None = None
    language_label: str | None = None
    assessment_id: str | None = None
    score: float | None = None
    issued_at: str
    issued_by: str = "auto"

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": 12,
                    "display_name": "Jane Doe",
                    "level": "intermediate",
                    "language_code": "py",
                    "language_label": "Python",
                    "assessment_id": "550e8400-e29b-41d4-a716-446655440000",
                    "score": 0.92,
                    "issued_at": "2026-06-22T12:00:00+00:00",
                    "issued_by": "auto",
                }
            ]
        }
    )
