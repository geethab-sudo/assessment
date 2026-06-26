"""Platform-wide settings stored in MongoDB (admin-configurable)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

SETTINGS_KEY_CERTIFICATE_ISSUER = "certificate_issuer"

DEFAULT_ORGANIZATION_NAME = "Wekan Enterprise Solutions"
DEFAULT_VERIFICATION_INTRO = (
    "This page confirms that a certificate was issued by Wekan Enterprise Solutions. "
    "Share this URL or scan the QR code to prove authenticity — similar to Coursera "
    "or LinkedIn Learning credentials."
)


def _env_organization_name() -> str | None:
    value = (os.environ.get("CERTIFICATE_ORG_NAME") or "").strip()
    return value or None


def default_certificate_issuer_settings() -> dict[str, str]:
    org = _env_organization_name() or DEFAULT_ORGANIZATION_NAME
    intro = DEFAULT_VERIFICATION_INTRO
    if org != DEFAULT_ORGANIZATION_NAME:
        intro = (
            f"This page confirms that a certificate was issued by {org}. "
            "Share this URL or scan the QR code to prove authenticity — similar to "
            "Coursera or LinkedIn Learning credentials."
        )
    return {
        "organization_name": org,
        "verification_intro": intro,
    }


def get_certificate_issuer_settings() -> dict[str, str]:
    from services.database import coll

    defaults = default_certificate_issuer_settings()
    row = coll("platform_settings").find_one({"key": SETTINGS_KEY_CERTIFICATE_ISSUER})
    if not row:
        return defaults
    org = (row.get("organization_name") or defaults["organization_name"]).strip()
    intro = (row.get("verification_intro") or defaults["verification_intro"]).strip()
    return {
        "organization_name": org or defaults["organization_name"],
        "verification_intro": intro or defaults["verification_intro"],
    }


def save_certificate_issuer_settings(
    *,
    organization_name: str,
    verification_intro: str | None = None,
) -> dict[str, str]:
    from services.database import coll

    org = organization_name.strip()
    if not org:
        raise ValueError("organization_name is required")

    defaults = default_certificate_issuer_settings()
    intro = (verification_intro or defaults["verification_intro"]).strip()
    if not intro:
        raise ValueError("verification_intro is required")

    now = datetime.now(timezone.utc).isoformat()
    coll("platform_settings").update_one(
        {"key": SETTINGS_KEY_CERTIFICATE_ISSUER},
        {
            "$set": {
                "key": SETTINGS_KEY_CERTIFICATE_ISSUER,
                "organization_name": org,
                "verification_intro": intro,
                "updated_at": now,
            }
        },
        upsert=True,
    )
    return {
        "organization_name": org,
        "verification_intro": intro,
    }


def ensure_default_certificate_issuer_settings() -> None:
    """Insert default issuer settings when the collection is empty (idempotent)."""
    from services.database import coll

    if coll("platform_settings").find_one({"key": SETTINGS_KEY_CERTIFICATE_ISSUER}):
        return
    defaults = default_certificate_issuer_settings()
    now = datetime.now(timezone.utc).isoformat()
    coll("platform_settings").insert_one(
        {
            "key": SETTINGS_KEY_CERTIFICATE_ISSUER,
            **defaults,
            "updated_at": now,
        }
    )
