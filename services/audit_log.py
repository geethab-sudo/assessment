"""
Structured security audit logging.

Events are written to the ``audit`` logger as single-line JSON for easy ingestion.
Configure ``AUDIT_LOG_LEVEL`` (default INFO) and optional ``AUDIT_LOG_FILE``.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from starlette.requests import Request

_audit_logger: logging.Logger | None = None


def _logger() -> logging.Logger:
    global _audit_logger
    if _audit_logger is None:
        configure_audit_logging()
    assert _audit_logger is not None
    return _audit_logger


def configure_audit_logging() -> None:
    """Configure the audit logger once at application startup."""
    global _audit_logger
    if _audit_logger is not None:
        return

    logger = logging.getLogger("audit")
    level_name = (os.environ.get("AUDIT_LOG_LEVEL") or "INFO").upper()
    logger.setLevel(getattr(logging, level_name, logging.INFO))
    logger.propagate = False

    if not logger.handlers:
        handler: logging.Handler
        log_file = (os.environ.get("AUDIT_LOG_FILE") or "").strip()
        if log_file:
            handler = logging.FileHandler(log_file)
        else:
            handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)

    _audit_logger = logger


def client_ip(request: Request | None) -> str:
    if request is None:
        return "unknown"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def audit_event(
    event: str,
    *,
    request: Request | None = None,
    actor: str | None = None,
    role: str | None = None,
    method: str | None = None,
    path: str | None = None,
    status: str = "success",
    detail: str | None = None,
    **extra: Any,
) -> None:
    """Emit a structured audit log entry."""
    payload: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "status": status,
    }
    if request is not None:
        payload["ip"] = client_ip(request)
        payload["method"] = request.method
        payload["path"] = request.url.path
    if method:
        payload["method"] = method
    if path:
        payload["path"] = path
    if actor:
        payload["actor"] = actor
    if role:
        payload["role"] = role
    if detail:
        payload["detail"] = detail
    payload.update(extra)
    _logger().info(json.dumps(payload, default=str))


def auth_login_success(request: Request, *, role: str, actor: str | None = None) -> None:
    audit_event(
        "auth.login.success",
        request=request,
        role=role,
        actor=actor or role,
        status="success",
    )


def auth_login_failure(
    request: Request,
    *,
    role: str,
    reason: str,
    actor: str | None = None,
) -> None:
    audit_event(
        "auth.login.failure",
        request=request,
        role=role,
        actor=actor,
        status="failure",
        detail=reason,
    )


def auth_denied(
    request: Request,
    *,
    reason: str,
    role: str | None = None,
) -> None:
    audit_event(
        "auth.denied",
        request=request,
        role=role,
        status="failure",
        detail=reason,
    )


def admin_action(
    request: Request,
    *,
    action: str,
    resource: str | None = None,
    resource_id: str | int | None = None,
) -> None:
    extra: dict[str, Any] = {}
    if resource:
        extra["resource"] = resource
    if resource_id is not None:
        extra["resource_id"] = resource_id
    audit_event(
        f"admin.{action}",
        request=request,
        role="admin",
        actor="admin",
        status="success",
        **extra,
    )


def rate_limit_exceeded(request: Request, *, limit: int, window_seconds: int) -> None:
    audit_event(
        "rate_limit.exceeded",
        request=request,
        status="failure",
        detail=f"limit={limit}/{window_seconds}s",
    )
