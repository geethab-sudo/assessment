"""Certificate template layout calibration (admin)."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class TextFieldLayout(BaseModel):
    x_ratio: float = Field(..., ge=0, le=1)
    y_ratio: float = Field(..., ge=0, le=1)
    anchor: str = Field(default="center")
    size: int = Field(..., ge=8, le=120)
    color: str = Field(default="#1a1a1a")

    @field_validator("anchor")
    @classmethod
    def normalize_anchor(cls, v: str) -> str:
        a = (v or "center").strip().lower()
        if a not in ("center", "left", "right", "baseline"):
            raise ValueError("anchor must be center, left, right, or baseline")
        return a


class SignatureFieldLayout(BaseModel):
    x_ratio: float = Field(..., ge=0, le=1)
    y_ratio: float = Field(..., ge=0, le=1)
    anchor: str = Field(default="center")
    max_width_ratio: float = Field(default=0.14, ge=0.05, le=0.5)
    max_height_ratio: float = Field(default=0.06, ge=0.02, le=0.25)

    @field_validator("anchor")
    @classmethod
    def normalize_anchor(cls, v: str) -> str:
        a = (v or "center").strip().lower()
        if a not in ("center", "left", "right"):
            raise ValueError("anchor must be center, left, or right")
        return a


class TemplateLayoutBody(BaseModel):
    display_name: TextFieldLayout
    issue_date: TextFieldLayout
    signature: SignatureFieldLayout


class CertificateLayoutSavedResponse(BaseModel):
    ok: bool = True
    filename: str


class CertificateTemplatePreviewBody(BaseModel):
    display_name: str = Field(default="Sample Name", min_length=1, max_length=256)
    layout: TemplateLayoutBody | None = None

    @field_validator("display_name", mode="before")
    @classmethod
    def strip_name(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip()
        return v


class CertificateTemplateItem(BaseModel):
    filename: str
    width: int
    height: int
    calibrated: bool
    levels: list[str] = Field(default_factory=list)
    layout: TemplateLayoutBody | None = None


class CertificateTemplateListResponse(BaseModel):
    templates: list[CertificateTemplateItem]
    uncalibrated_count: int
    signature_file: str
    signature_present: bool
