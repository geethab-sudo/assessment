"""Pytest bootstrap — shared by all tests under this folder.

Loads ``.env``, connects to MongoDB Atlas using database ``test_db``, and
ensures indexes exist before the suite runs. Pure unit tests that mock the DB
are unaffected; integration tests use helpers in ``mongo_helpers.py``.

See TEST_GUIDE.md for how to run the suite.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

TEST_DB_NAME = "test_db"


def pytest_configure(config: pytest.Config) -> None:
    """Point all tests at Atlas ``test_db`` before any app or service imports."""
    load_dotenv(_ROOT / ".env", override=False)
    os.environ["MONGODB_DB_NAME"] = TEST_DB_NAME
    # Ensure dev database name from .env cannot leak into test workers.
    assert os.environ["MONGODB_DB_NAME"] == TEST_DB_NAME
    uri = (os.environ.get("MONGODB_URI") or os.environ.get("MONGODB_URL") or "").strip()
    if not uri:
        pytest.exit(
            "MONGODB_URI must be set in .env to run tests (uses database: test_db).",
            returncode=1,
        )
    from services import database as db

    db.reset_client()


@pytest.fixture(scope="session", autouse=True)
def mongodb_test_session() -> None:
    """Verify Atlas connectivity and create indexes on test_db once per run."""
    from services.database import init_db, ping_database

    if not ping_database():
        pytest.fail(
            "Cannot reach MongoDB Atlas. Check MONGODB_URI and Network Access."
        )
    init_db()


@pytest.fixture
def mongo_clean():
    """Clear all collections — use in integration tests that need a blank slate."""
    from tests.mongo_helpers import clear_all_collections

    clear_all_collections()
    yield
    clear_all_collections()
