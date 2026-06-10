"""Add standard HTTP security response headers."""

from __future__ import annotations

import os

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# Relaxed CSP for Swagger UI / ReDoc (inline scripts and CDN assets).
_DOCS_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https://cdn.jsdelivr.net; "
    "font-src 'self' https://cdn.jsdelivr.net"
)

# Strict CSP for API responses (JSON only).
_API_CSP = "default-src 'none'; frame-ancestors 'none'"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        path = request.url.path
        is_docs = path in ("/docs", "/redoc", "/openapi.json")

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = _DOCS_CSP if is_docs else _API_CSP

        if os.environ.get("ENABLE_HSTS", "").strip().lower() in ("1", "true", "yes"):
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response
