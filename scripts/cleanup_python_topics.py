#!/usr/bin/env python3
"""
Clean up orphaned Python topics from the database that are no longer defined
in seed_sample_catalog.py's Python topic list.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=True)

from services.database import coll, init_db
from scripts.seed_sample_catalog import SAMPLE


def main() -> None:
    init_db()
    deleted_count = 0

    py_block = next((b for b in SAMPLE if b["code"] == "py"), None)
    if not py_block:
        print("Error: Could not find Python ('py') catalog block in seed_sample_catalog.py.")
        sys.exit(1)

    seed_topic_names = {t["name"] for t in py_block["topics"]}

    lang = coll("languages").find_one({"code": "py"})
    if not lang:
        print("Python language not found in database. Nothing to clean up.")
        return

    db_topics = list(coll("topics").find({"language_id": lang["id"]}))
    for db_topic in db_topics:
        if db_topic["name"] not in seed_topic_names:
            coll("topics").delete_one({"id": db_topic["id"]})
            print(f"Deleting orphaned topic: '{db_topic['name']}'")
            deleted_count += 1

    print(f"Done. Deleted {deleted_count} orphaned Python topics from the database.")


if __name__ == "__main__":
    main()
