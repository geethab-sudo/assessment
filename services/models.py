"""SQLAlchemy models for assessments, submissions, languages, and topics."""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
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
    modality: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'pyodide'"),
    )
    #: Optional editor for coding questions: "shell" (bash) or "powershell"; NULL = assessment language
    coding_editor_language: Mapped[str | None] = mapped_column(String(32), nullable=True)

    language: Mapped["Language"] = relationship("Language", back_populates="topics")

    __table_args__ = (
        UniqueConstraint("language_id", "name", name="uq_topic_name_per_language"),
        Index("ix_topics_name", "name"),
    )


class QuestionBank(Base):
    """
    Canonical, reusable question store.

    Every confirmed assessment question is automatically upserted here.
    Deduplication key: SHA-256 of (type | topic_name | question_text[:1000]).
    Statistics counters are updated atomically when submissions are graded.
    """

    __tablename__ = "question_bank"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    #: SHA-256 hex digest — deduplication key so identical questions are not duplicated
    content_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)  # mcq / coding / subjective
    options: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("''") 
    )
    correct_answer: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("''")
    )
    code_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    topic_name: Mapped[str] = mapped_column(
        String(512), nullable=False, server_default=text("''")
    )
    language_code: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True
    )
    #: Level label stored here: beginner / intermediate / advanced
    difficulty: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)
    #: How many assessments have included this question
    times_used: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    #: How many times a participant answered it correctly
    times_correct: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    #: How many times a participant answered it incorrectly
    times_wrong: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )

    __table_args__ = (
        Index("ix_question_bank_topic_difficulty", "topic_name", "difficulty"),
    )


class EmployeeQuestionMastery(Base):
    """
    Per-employee record of bank questions answered correctly (mastered).

    Populated on submit when a graded answer is correct; used for bank exclusion
    without rescanning all submissions.
    """

    __tablename__ = "employee_question_mastery"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    #: Normalized employee id (casefold), same convention as assessment_attempts
    employee_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    bank_question_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("question_bank.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mastered_at: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "employee_id",
            "bank_question_id",
            name="uq_employee_bank_mastery",
        ),
    )


class Assessment(Base):
    __tablename__ = "assessments"

    #: ASM-XXXXXXXX for new assessments; legacy rows may use UUID strings
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
    routing_flag: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'pyodide'"),
    )
    is_timed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notebook_grace_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    questions: Mapped[list["AssessmentQuestion"]] = relationship(
        "AssessmentQuestion",
        back_populates="assessment",
        cascade="all, delete-orphan",
    )
    attempts: Mapped[list["AssessmentAttempt"]] = relationship(
        "AssessmentAttempt",
        back_populates="assessment",
        cascade="all, delete-orphan",
    )

    __table_args__ = (Index("ix_assessments_created_at", "created_at"),)


class AssessmentAttempt(Base):
    """Per-participant timed session (assessment_id + employee_id)."""

    __tablename__ = "assessment_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assessment_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("assessments.assessment_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    employee_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    started_at: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[str] = mapped_column(String(64), nullable=False)
    notebook_expires_at: Mapped[str] = mapped_column(String(64), nullable=False)
    submitted_at: Mapped[str | None] = mapped_column(String(64), nullable=True)

    assessment: Mapped["Assessment"] = relationship("Assessment", back_populates="attempts")

    __table_args__ = (
        UniqueConstraint("assessment_id", "employee_id", name="uq_assessment_attempt_employee"),
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
    #: Catalog topic name this question was generated for (empty for legacy questions)
    topic_name: Mapped[str] = mapped_column(String(512), nullable=False, server_default=text("''"))
    #: Optional code block for MCQ stems (and other types); shown highlighted in the UI
    code_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: FK to question_bank if this question came from or was added to the bank (NULL for legacy)
    bank_question_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("question_bank.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    #: Difficulty level stored at generation time: beginner / intermediate / advanced
    difficulty: Mapped[str | None] = mapped_column(String(32), nullable=True)

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
    routing_flag: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'pyodide'"),
    )
    # Optional raw notebook JSON for audit/debugging (nullable)
    raw_notebook: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, server_default=text("NULL"),
    )
    #: Client session that submitted (for admin reporting)
    submitter_client_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    __table_args__ = (
        Index("ix_submissions_assessment_id_user_id", "assessment_id", "user_id"),
        Index("ix_submissions_timestamp", "timestamp"),
    )
