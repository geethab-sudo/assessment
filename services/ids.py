"""Shared ID helpers: client identifiers and assessment IDs."""

from __future__ import annotations

import re
import secrets
import uuid

_ASM_PREFIX = "ASM-"
_ASM_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_ASM_NANOID_SIZE = 8
_ASM_ID_RE = re.compile(rf"^{re.escape(_ASM_PREFIX)}[{_ASM_ALPHABET}]{{{_ASM_NANOID_SIZE}}}$")


def sanitize_client_id(raw: str) -> str:
    """
    Safe client id: letters, digits, underscore, hyphen (max 64 chars).
    """
    s = raw.strip()
    if not s:
        raise ValueError("client_id is required")
    if len(s) > 64:
        raise ValueError("client_id must be at most 64 characters")
    allowed = frozenset(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    )
    if not all(c in allowed for c in s):
        raise ValueError(
            "client_id may only contain letters, digits, underscore, and hyphen"
        )
    return s


def generate_assessment_id() -> str:
    """Return a new assessment id: ASM- + 8-char uppercase NanoID-style token."""
    token = "".join(
        secrets.choice(_ASM_ALPHABET) for _ in range(_ASM_NANOID_SIZE)
    )
    return f"{_ASM_PREFIX}{token}"


def is_valid_assessment_id(raw: str) -> bool:
    """True for legacy UUIDs or new ASM-XXXXXXXX ids."""
    aid = raw.strip()
    if _ASM_ID_RE.fullmatch(aid):
        return True
    try:
        uuid.UUID(aid)
    except ValueError:
        return False
    return True


def normalize_assessment_id(raw: str) -> str:
    """Strip and validate assessment id; raises ValueError when invalid."""
    aid = raw.strip()
    if not is_valid_assessment_id(aid):
        raise ValueError("Invalid assessment ID format")
    return aid
