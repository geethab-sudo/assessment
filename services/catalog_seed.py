"""Idempotent sample catalog seeding (shared by API startup and scripts)."""

from __future__ import annotations

import logging
import os
from typing import Any

from services.catalog_seed_data import SAMPLE_CATALOG
from services.database import coll, get_database_name, next_id

logger = logging.getLogger(__name__)


def _auto_seed_enabled() -> bool:
    return os.environ.get("AUTO_SEED_CATALOG", "true").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def apply_sample_catalog() -> dict[str, int]:
    """
    Insert or update default languages/topics. Safe to call on every startup.
    Never deletes existing catalog rows.
    """
    created_lang = 0
    created_topic = 0
    skipped_lang = 0
    skipped_topic = 0

    for block in SAMPLE_CATALOG:
        code = block["code"]
        name = block["name"]
        lang = coll("languages").find_one({"code": code})
        if not lang:
            lang = {
                "id": next_id("languages"),
                "code": code,
                "name": name,
            }
            coll("languages").insert_one(lang)
            created_lang += 1
        else:
            skipped_lang += 1

        lid = lang["id"]
        for t in block["topics"]:
            tname = t["name"]
            docs = t.get("related_documents") or []
            modality = t.get("modality", "pyodide")
            coding_editor = t.get("coding_editor_language")
            if coding_editor:
                coding_editor = str(coding_editor).strip().lower()
                if coding_editor not in ("shell", "powershell"):
                    coding_editor = None
            existing = coll("topics").find_one({"language_id": lid, "name": tname})
            if existing:
                coll("topics").update_one(
                    {"id": existing["id"]},
                    {
                        "$set": {
                            "modality": modality,
                            "related_documents": docs,
                            "coding_editor_language": coding_editor,
                        }
                    },
                )
                skipped_topic += 1
                continue
            coll("topics").insert_one(
                {
                    "id": next_id("topics"),
                    "language_id": lid,
                    "name": tname,
                    "related_documents": docs,
                    "modality": modality,
                    "coding_editor_language": coding_editor,
                }
            )
            created_topic += 1

    return {
        "created_lang": created_lang,
        "created_topic": created_topic,
        "skipped_lang": skipped_lang,
        "skipped_topic": skipped_topic,
    }


def ensure_default_catalog() -> dict[str, Any] | None:
    """
    Ensure the reference catalog exists on the active database.
    Called from ``init_db`` so dev/prod API startup self-heals an empty catalog.
    """
    if not _auto_seed_enabled():
        return None

    db_name = get_database_name()
    lang_count = coll("languages").count_documents({})
    if lang_count > 0:
        # Still repair any missing preset topics without touching existing rows.
        stats = apply_sample_catalog()
        if stats["created_topic"] or stats["created_lang"]:
            logger.info(
                "Catalog repair on %s: +%s languages, +%s topics",
                db_name,
                stats["created_lang"],
                stats["created_topic"],
            )
        return {"repaired": True, **stats}

    stats = apply_sample_catalog()
    logger.warning(
        "Catalog was empty on database %r — seeded default languages/topics "
        "(+%s languages, +%s topics). Set AUTO_SEED_CATALOG=false to disable.",
        db_name,
        stats["created_lang"],
        stats["created_topic"],
    )
    return {"seeded_empty": True, **stats}
