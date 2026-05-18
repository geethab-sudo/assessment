"""
JWT auth for admin vs client API access. Set in .env:
  JWT_SECRET=<long random string>
  ADMIN_PASSWORD=<admin portal password>

Clients sign in with their client_id only (same format as admin uses when generating assessments).
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

JWT_ALG = "HS256"
JWT_EXPIRE_HOURS = 24


def _jwt_secret() -> str:
    s = (os.environ.get("JWT_SECRET") or "").strip()
    if not s:
        raise RuntimeError(
            "JWT_SECRET is not set. Add a long random string to your .env file."
        )
    return s


def create_access_token(role: str, *, client_id: str | None = None) -> str:
    if role not in ("admin", "client"):
        raise ValueError("invalid role")
    if role == "client":
        if not (client_id or "").strip():
            raise ValueError("client_id required for client role")
    elif client_id is not None:
        raise ValueError("client_id must not be set for admin role")
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "role": role,
        "exp": now + timedelta(hours=JWT_EXPIRE_HOURS),
        "iat": now,
    }
    if role == "client":
        payload["client_id"] = client_id
    return jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALG)


def decode_token_payload(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALG])
    except jwt.PyJWTError as e:
        raise ValueError("invalid token") from e
    return payload


def decode_token_get_role(token: str) -> str:
    payload = decode_token_payload(token)
    role = payload.get("role")
    if role not in ("admin", "client"):
        raise ValueError("invalid token role")
    return str(role)


def decode_token_get_client_id(token: str) -> str | None:
    payload = decode_token_payload(token)
    if payload.get("role") != "client":
        return None
    cid = payload.get("client_id")
    return str(cid).strip() if cid else None


def jwt_configured() -> bool:
    return bool((os.environ.get("JWT_SECRET") or "").strip())


def admin_password_configured() -> bool:
    return bool((os.environ.get("ADMIN_PASSWORD") or "").strip())


def verify_admin_password(password: str) -> bool:
    expected = (os.environ.get("ADMIN_PASSWORD") or "").strip()
    if not expected:
        return False
    try:
        return secrets.compare_digest(password, expected)
    except TypeError:
        return False
