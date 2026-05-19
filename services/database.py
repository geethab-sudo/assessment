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
    _ensure_assessments_creation_mode_column(eng)


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


def _ensure_assessments_creation_mode_column(eng) -> None:
    """Add creation_mode for DBs created before manual assessments."""
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'assessments'
                          AND column_name = 'creation_mode'
                    ) THEN
                        ALTER TABLE assessments
                        ADD COLUMN creation_mode VARCHAR(16) NULL
                        DEFAULT 'generated';
                    END IF;
                END $$;
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
