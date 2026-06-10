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

load_dotenv(ROOT / ".env")
load_dotenv(override=True)

from sqlalchemy import select

from services.database import init_db, get_session_factory
from services.models import Language, Topic
from scripts.seed_sample_catalog import SAMPLE


def main() -> None:
    init_db()
    sf = get_session_factory()
    deleted_count = 0

    # Extract the Python topic names from the seed catalog
    py_block = next((b for b in SAMPLE if b["code"] == "py"), None)
    if not py_block:
        print("Error: Could not find Python ('py') catalog block in seed_sample_catalog.py.")
        sys.exit(1)

    seed_topic_names = {t["name"] for t in py_block["topics"]}

    with sf() as session:
        # Find the Python language record
        lang = session.scalar(select(Language).where(Language.code == "py"))
        if not lang:
            print("Python language not found in database. Nothing to clean up.")
            return

        # Fetch all database topics for Python
        db_topics = session.scalars(
            select(Topic).where(Topic.language_id == lang.id)
        ).all()

        # Delete any database topic that is not in the seed definition
        for db_topic in db_topics:
            if db_topic.name not in seed_topic_names:
                session.delete(db_topic)
                print(f"Deleting orphaned topic: '{db_topic.name}'")
                deleted_count += 1

        session.commit()

    print(f"Done. Deleted {deleted_count} orphaned Python topics from the database.")


if __name__ == "__main__":
    main()
