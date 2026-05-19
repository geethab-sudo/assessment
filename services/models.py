"""SQLAlchemy models for assessments, submissions, languages, and topics."""

from __future__ import annotations

from typing import Any

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from services.database import Base


class Language(Base):
    """Supported languages (human or course locale); `code` and `name` are required."""

    __tablename__ = "languages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)

    topics: Mapped[list["Topic"]] = relationship(
        "Topic", back_populates="language", cascade="all, delete-orphan"
    )


class Topic(Base):
    """Topic under a language; `related_documents` is JSONB (e.g. list of {title, url?, path?})."""

    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    language_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("languages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    related_documents: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )

    language: Mapped["Language"] = relationship("Language", back_populates="topics")

    __table_args__ = (
        UniqueConstraint("language_id", "name", name="uq_topic_name_per_language"),
    )


class Assessment(Base):
    __tablename__ = "assessments"

    #: UUID string from generation
    assessment_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    #: If set, only this client may open/submit; NULL = shared (any client)
    owner_client_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    #: Catalog `languages.code` at generation (syntax highlighting for coding items); optional for legacy
    language_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: Human-readable language at generation (e.g. "Python (py)"); optional for legacy
    language_label: Mapped[str | None] = mapped_column(String(256), nullable=True)
    #: Catalog topic titles (or one-line custom topic preview), in selection order
    topic_names: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    #: UTC ISO timestamp when assessment row was first created.
    created_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: `generated` (LLM) or `manual` (admin-authored questions).
    creation_mode: Mapped[str | None] = mapped_column(
        String(16), nullable=True, server_default=text("'generated'")
    )

    questions: Mapped[list["AssessmentQuestion"]] = relationship(
        "AssessmentQuestion",
        back_populates="assessment",
        cascade="all, delete-orphan",
    )


class AssessmentQuestion(Base):
    __tablename__ = "assessment_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assessment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("assessments.assessment_id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[str] = mapped_column(String(64), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    options: Mapped[str] = mapped_column(Text, default="")
    correct_answer: Mapped[str] = mapped_column(Text, default="")

    assessment: Mapped["Assessment"] = relationship("Assessment", back_populates="questions")

    __table_args__ = (
        UniqueConstraint("assessment_id", "question_id", name="uq_assessment_question_id"),
    )


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assessment_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(256), nullable=False)
    question_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_answer: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[str] = mapped_column(String(32), default="")
    feedback: Mapped[str] = mapped_column(Text, default="")
    timestamp: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Client session that submitted (for admin reporting)
    submitter_client_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
