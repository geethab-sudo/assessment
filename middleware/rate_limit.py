"""In-memory per-IP rate limiting for sensitive endpoints."""

from __future__ import annotations

import os
import time
from collections import defaultdict
from collections.abc import Callable
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from services import audit_log

# (max_requests, window_seconds)
DEFAULT_RULE: tuple[int, int] = (120, 60)
ENDPOINT_RULES: dict[str, tuple[int, int]] = {
    "/auth/login": (10, 60),
    "/submit-assessment": (30, 60),
    "/submit-notebook-assessment": (20, 60),
    "/generate-assessment": (10, 60),
}


def _rate_limit_enabled() -> bool:
    return os.environ.get("RATE_LIMIT_ENABLED", "true").strip().lower() not in (
        "0",
        "false",
        "no",
    )


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app) -> None:
        super().__init__(app)
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not _rate_limit_enabled() or request.method in ("OPTIONS", "HEAD"):
            return await call_next(request)

        path = request.url.path
        limit, window = ENDPOINT_RULES.get(path, DEFAULT_RULE)
        key = f"{_client_ip(request)}:{path}"
        now = time.monotonic()

        with self._lock:
            timestamps = [t for t in self._hits[key] if now - t < window]
            if len(timestamps) >= limit:
                audit_log.rate_limit_exceeded(request, limit=limit, window_seconds=window)
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests. Please try again later."},
                    headers={"Retry-After": str(window)},
                )
            timestamps.append(now)
            self._hits[key] = timestamps

        return await call_next(request)


def rate_limit_rule_for_path(path: str) -> tuple[int, int]:
    """Return the configured (limit, window) for a path (used in tests)."""
    return ENDPOINT_RULES.get(path, DEFAULT_RULE)
