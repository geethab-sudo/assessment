"""Tests for catalog auto-seed and test DB safety guards."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.catalog_seed import apply_sample_catalog, ensure_default_catalog  # noqa: E402
from tests.mongo_helpers import TEST_DB_NAME, clear_all_collections  # noqa: E402


class TestCatalogSeed(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["MONGODB_DB_NAME"] = TEST_DB_NAME
        from services.database import reset_client

        reset_client()
        clear_all_collections()

    def tearDown(self) -> None:
        os.environ["MONGODB_DB_NAME"] = TEST_DB_NAME
        from services.database import reset_client

        reset_client()
        clear_all_collections()

    def test_ensure_default_catalog_seeds_empty_database(self) -> None:
        from services.database import coll, init_db

        init_db()
        self.assertGreater(coll("languages").count_documents({}), 0)
        py = coll("languages").find_one({"code": "py"})
        self.assertIsNotNone(py)
        topic_count = coll("topics").count_documents({"language_id": py["id"]})
        self.assertGreaterEqual(topic_count, 6)

    def test_apply_sample_catalog_is_idempotent(self) -> None:
        from services.database import coll, init_db

        init_db()
        before_topics = coll("topics").count_documents({})
        second = apply_sample_catalog()
        self.assertEqual(second["created_lang"], 0)
        self.assertEqual(second["created_topic"], 0)
        self.assertEqual(coll("topics").count_documents({}), before_topics)

    def test_clear_all_collections_refuses_dev_database(self) -> None:
        os.environ["MONGODB_DB_NAME"] = "assesment"
        from services.database import reset_client

        reset_client()
        with self.assertRaises(RuntimeError):
            clear_all_collections()
        os.environ["MONGODB_DB_NAME"] = TEST_DB_NAME
        reset_client()


if __name__ == "__main__":
    unittest.main()
