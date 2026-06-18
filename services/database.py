"""
PostgreSQL connection and schema creation (SQLAlchemy 2).
Set DATABASE_URL, e.g. postgresql+psycopg://user:pass@localhost:5432/assesment
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


_engine = None
SessionLocal = None


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Example: "
            "postgresql+psycopg://postgres:postgres@localhost:5432/assesment"
        )
    # Heroku-style URLs
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://") :]
    return url


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(
            get_database_url(),
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
    return _engine


def get_session_factory():
    global SessionLocal
    if SessionLocal is None:
        SessionLocal = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
    return SessionLocal


def init_db() -> None:
    """Create tables if they do not exist."""
    # Import models so they register with Base.metadata
    from services import models  # noqa: F401

    get_engine()
    eng = get_engine()
    Base.metadata.create_all(bind=eng)
    _ensure_assessments_language_code_column(eng)
    _ensure_assessments_catalog_meta_columns(eng)
    _ensure_assessments_created_at_column(eng)
    _ensure_modality_and_routing_columns(eng)
    _ensure_raw_notebook_column(eng)
    _ensure_question_topic_name_column(eng)
    _ensure_assessment_timed_columns(eng)
    _ensure_allow_pyodide_paste_column(eng)
    _ensure_assessment_attempts_table(eng)
    _ensure_topic_coding_editor_language_column(eng)
    _ensure_question_code_snippet_column(eng)
    _ensure_agents_table(eng)
    _ensure_required_indexes(eng)
    _ensure_question_bank_table(eng)           # must run before FK column below
    _ensure_assessment_question_bank_columns(eng)
    _backfill_question_bank_difficulty_labels(eng)
    _backfill_question_bank_from_assessment_questions_if_needed(eng)
    _ensure_employee_question_mastery_table(eng)
    _backfill_employee_question_mastery_if_empty(eng)
    from services.agent_service import seed_default_agent_from_env

    seed_default_agent_from_env()


def _ensure_raw_notebook_column(eng) -> None:
    """Add raw_notebook column to submissions table if it does not exist (PostgreSQL)."""
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'submissions' AND column_name = 'raw_notebook'
                    ) THEN
                        ALTER TABLE submissions ADD COLUMN raw_notebook JSONB NULL;
                    END IF;
                END $$;
                """
            )
        )


def _ensure_assessments_language_code_column(eng) -> None:
    """For existing DBs created before language_code, add the column (PostgreSQL)."""
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'assessments' AND column_name = 'language_code'
                    ) THEN
                        ALTER TABLE assessments ADD COLUMN language_code VARCHAR(32) NULL;
                    END IF;
                END $$;
                """
            )
        )


def _ensure_assessments_catalog_meta_columns(eng) -> None:
    """Add language_label and topic_names for DBs created before catalog metadata on assessments."""
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'assessments' AND column_name = 'language_label'
                    ) THEN
                        ALTER TABLE assessments ADD COLUMN language_label VARCHAR(256) NULL;
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'assessments' AND column_name = 'topic_names'
                    ) THEN
                        ALTER TABLE assessments
                        ADD COLUMN topic_names JSONB NOT NULL DEFAULT '[]'::jsonb;
                    END IF;
                END $$;
                """
            )
        )


def _ensure_assessments_created_at_column(eng) -> None:
    """Add created_at for DBs created before assessment timestamps were stored."""
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'assessments' AND column_name = 'created_at'
                    ) THEN
                        ALTER TABLE assessments ADD COLUMN created_at VARCHAR(64) NULL;
                    END IF;
                END $$;
                """
            )
        )
def _ensure_modality_and_routing_columns(eng) -> None:
    """Add modality to topics, and routing_flag to assessments and submissions if they do not exist (PostgreSQL)."""
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'topics' AND column_name = 'modality'
                    ) THEN
                        ALTER TABLE topics ADD COLUMN modality VARCHAR(32) NOT NULL DEFAULT 'pyodide';
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'assessments' AND column_name = 'routing_flag'
                    ) THEN
                        ALTER TABLE assessments ADD COLUMN routing_flag VARCHAR(32) NOT NULL DEFAULT 'pyodide';
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'submissions' AND column_name = 'routing_flag'
                    ) THEN
                        ALTER TABLE submissions ADD COLUMN routing_flag VARCHAR(32) NOT NULL DEFAULT 'pyodide';
                    END IF;
                END $$;
                """
            )
        )


def _ensure_question_topic_name_column(eng) -> None:
    """Add topic_name to assessment_questions for per-topic question attribution."""
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'assessment_questions' AND column_name = 'topic_name'
                    ) THEN
                        ALTER TABLE assessment_questions
                        ADD COLUMN topic_name VARCHAR(512) NOT NULL DEFAULT '';
                    END IF;
                END $$;
                """
            )
        )


def _ensure_assessment_timed_columns(eng) -> None:
    """Add timed-assessment config columns to assessments."""
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'assessments' AND column_name = 'is_timed'
                    ) THEN
                        ALTER TABLE assessments
                        ADD COLUMN is_timed BOOLEAN NOT NULL DEFAULT false;
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'assessments' AND column_name = 'duration_minutes'
                    ) THEN
                        ALTER TABLE assessments ADD COLUMN duration_minutes INTEGER NULL;
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'assessments' AND column_name = 'notebook_grace_minutes'
                    ) THEN
                        ALTER TABLE assessments ADD COLUMN notebook_grace_minutes INTEGER NULL;
                    END IF;
                END $$;
                """
            )
        )


def _ensure_allow_pyodide_paste_column(eng) -> None:
    """Per-assessment opt-in for paste in in-browser coding editors."""
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'assessments'
                          AND column_name = 'allow_pyodide_paste'
                    ) THEN
                        ALTER TABLE assessments
                        ADD COLUMN allow_pyodide_paste BOOLEAN NOT NULL DEFAULT false;
                    END IF;
                END $$;
                """
            )
        )


def _ensure_topic_coding_editor_language_column(eng) -> None:
    """Add coding_editor_language to topics (shell / powershell for terminal-style coding)."""
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'topics' AND column_name = 'coding_editor_language'
                    ) THEN
                        ALTER TABLE topics ADD COLUMN coding_editor_language VARCHAR(32) NULL;
                    END IF;
                END $$;
                """
            )
        )


def _ensure_question_code_snippet_column(eng) -> None:
    """Add code_snippet to assessment_questions for MCQ code blocks."""
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'assessment_questions'
                          AND column_name = 'code_snippet'
                    ) THEN
                        ALTER TABLE assessment_questions
                        ADD COLUMN code_snippet TEXT NULL;
                    END IF;
                END $$;
                """
            )
        )


def _ensure_agents_table(eng) -> None:
    """Create agents table if missing (also created by create_all on fresh DB)."""
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS agents (
                    id SERIAL PRIMARY KEY,
                    agent_name VARCHAR(64) NOT NULL UNIQUE,
                    api_key TEXT NOT NULL DEFAULT '',
                    status VARCHAR(16) NOT NULL DEFAULT 'Active',
                    is_selected BOOLEAN NOT NULL DEFAULT false,
                    created_at VARCHAR(64) NOT NULL,
                    updated_at VARCHAR(64) NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_agents_agent_name ON agents (agent_name);
                """
            )
        )


def _ensure_question_bank_table(eng) -> None:
    """Create question_bank table and its indexes if they do not exist."""
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS question_bank (
                    id             SERIAL PRIMARY KEY,
                    content_hash   VARCHAR(64) NOT NULL UNIQUE,
                    question_text  TEXT        NOT NULL,
                    type           VARCHAR(32) NOT NULL,
                    options        TEXT        NOT NULL DEFAULT '',
                    correct_answer TEXT        NOT NULL DEFAULT '',
                    code_snippet   TEXT        NULL,
                    topic_name     VARCHAR(512) NOT NULL DEFAULT '',
                    language_code  VARCHAR(32)  NULL,
                    difficulty     VARCHAR(32)  NOT NULL,
                    created_at     VARCHAR(64)  NOT NULL,
                    times_used     INTEGER NOT NULL DEFAULT 0,
                    times_correct  INTEGER NOT NULL DEFAULT 0,
                    times_wrong    INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS ix_question_bank_content_hash
                    ON question_bank (content_hash);
                CREATE INDEX IF NOT EXISTS ix_question_bank_language_code
                    ON question_bank (language_code);
                CREATE INDEX IF NOT EXISTS ix_question_bank_difficulty
                    ON question_bank (difficulty);
                CREATE INDEX IF NOT EXISTS ix_question_bank_topic_difficulty
                    ON question_bank (topic_name, difficulty);
                """
            )
        )


def _ensure_assessment_question_bank_columns(eng) -> None:
    """Add bank_question_id (FK) and difficulty columns to assessment_questions if missing."""
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'assessment_questions'
                          AND column_name = 'bank_question_id'
                    ) THEN
                        ALTER TABLE assessment_questions
                        ADD COLUMN bank_question_id INTEGER NULL
                            REFERENCES question_bank(id) ON DELETE SET NULL;
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'assessment_questions'
                          AND column_name = 'difficulty'
                    ) THEN
                        ALTER TABLE assessment_questions
                        ADD COLUMN difficulty VARCHAR(32) NULL;
                    END IF;
                END $$;
                CREATE INDEX IF NOT EXISTS ix_aq_bank_question_id
                    ON assessment_questions (bank_question_id);
                """
            )
        )


def _backfill_question_bank_difficulty_labels(eng) -> None:
    """Map legacy easy/medium/hard labels to beginner/intermediate/advanced."""
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE question_bank SET difficulty = 'beginner'
                    WHERE difficulty = 'easy';
                UPDATE question_bank SET difficulty = 'intermediate'
                    WHERE difficulty = 'medium';
                UPDATE question_bank SET difficulty = 'advanced'
                    WHERE difficulty = 'hard';

                UPDATE assessment_questions SET difficulty = 'beginner'
                    WHERE difficulty = 'easy';
                UPDATE assessment_questions SET difficulty = 'intermediate'
                    WHERE difficulty = 'medium';
                UPDATE assessment_questions SET difficulty = 'advanced'
                    WHERE difficulty = 'hard';
                """
            )
        )


def _ensure_employee_question_mastery_table(eng) -> None:
    """Per-employee mastered bank questions (employee_id + bank_question_id)."""
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS employee_question_mastery (
                    id               SERIAL PRIMARY KEY,
                    employee_id      VARCHAR(64) NOT NULL,
                    bank_question_id INTEGER NOT NULL
                        REFERENCES question_bank(id) ON DELETE CASCADE,
                    mastered_at      VARCHAR(64) NOT NULL,
                    CONSTRAINT uq_employee_bank_mastery
                        UNIQUE (employee_id, bank_question_id)
                );
                CREATE INDEX IF NOT EXISTS ix_eqm_employee_id
                    ON employee_question_mastery (employee_id);
                CREATE INDEX IF NOT EXISTS ix_eqm_bank_question_id
                    ON employee_question_mastery (bank_question_id);
                """
            )
        )


def _backfill_question_bank_from_assessment_questions_if_needed(eng) -> None:
    """Import legacy assessment questions into question_bank (one-time per row)."""
    with eng.connect() as conn:
        count = conn.execute(
            text(
                "SELECT COUNT(*) FROM assessment_questions WHERE bank_question_id IS NULL"
            )
        ).scalar()
    if not count or int(count) == 0:
        return
    from services import question_bank_service

    question_bank_service.backfill_question_bank_from_assessment_questions()


def _backfill_employee_question_mastery_if_empty(eng) -> None:
    """One-time populate mastery from historical correct submissions."""
    with eng.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM employee_question_mastery")
        ).scalar()
    if count and int(count) > 0:
        return
    from services import question_bank_service

    question_bank_service.backfill_employee_mastery_from_submissions()

def _ensure_required_indexes(eng) -> None:
    """Add btree indexes used by frequent filters/sorts (idempotent on PostgreSQL)."""
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_submissions_assessment_id_user_id
                    ON submissions (assessment_id, user_id);
                CREATE INDEX IF NOT EXISTS ix_submissions_timestamp
                    ON submissions (timestamp DESC);
                CREATE INDEX IF NOT EXISTS ix_topics_name
                    ON topics (name);
                CREATE INDEX IF NOT EXISTS ix_assessments_created_at
                    ON assessments (created_at DESC NULLS LAST);
                """
            )
        )


def _ensure_assessment_attempts_table(eng) -> None:
    """Create assessment_attempts if missing (also created by create_all on fresh DB)."""
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS assessment_attempts (
                    id SERIAL PRIMARY KEY,
                    assessment_id VARCHAR(36) NOT NULL
                        REFERENCES assessments(assessment_id) ON DELETE CASCADE,
                    employee_id VARCHAR(64) NOT NULL,
                    started_at VARCHAR(64) NOT NULL,
                    expires_at VARCHAR(64) NOT NULL,
                    notebook_expires_at VARCHAR(64) NOT NULL,
                    submitted_at VARCHAR(64) NULL,
                    CONSTRAINT uq_assessment_attempt_employee
                        UNIQUE (assessment_id, employee_id)
                );
                CREATE INDEX IF NOT EXISTS ix_assessment_attempts_assessment_id
                    ON assessment_attempts (assessment_id);
                CREATE INDEX IF NOT EXISTS ix_assessment_attempts_employee_id
                    ON assessment_attempts (employee_id);
                """
            )
        )


def ping_database() -> bool:
    try:
        eng = get_engine()
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
