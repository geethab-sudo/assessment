"""Shared validation for client identifiers (JWT / login)."""


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
