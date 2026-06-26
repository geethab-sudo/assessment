#!/usr/bin/env python3
"""
Insert sample languages and topics (with related_documents) for local development.
Safe to re-run: skips rows that already exist (by language code and topic name).

The API also runs the same logic on startup (see services.catalog_seed).

Usage (from project root, with MONGODB_URI in .env):
  python scripts/seed_sample_catalog.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env", override=True)

from services.catalog_seed import apply_sample_catalog  # noqa: E402
from services.database import init_db  # noqa: E402


def main() -> None:
    init_db()
    stats = apply_sample_catalog()
    print(
        "Done. Languages: {created_lang} created, {skipped_lang} already present. "
        "Topics: {created_topic} created, {skipped_topic} already present.".format(
            **stats
        )
    )


if __name__ == "__main__":
    main()
