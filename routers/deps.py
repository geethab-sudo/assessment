"""FastAPI dependencies for JWT authentication."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from services import audit_log, auth_service

security = HTTPBearer(auto_error=False)


def get_bearer_token(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        audit_log.auth_denied(request, reason="missing_or_invalid_scheme")
        raise HTTPException(status_code=401, detail="Not authenticated")
    return credentials.credentials


def require_admin(
    request: Request,
    token: Annotated[str, Depends(get_bearer_token)],
) -> None:
    try:
        role = auth_service.decode_token_get_role(token)
    except ValueError:
        audit_log.auth_denied(request, reason="invalid_or_expired_token")
        raise HTTPException(status_code=401, detail="Invalid or expired token") from None
    if role != "admin":
        audit_log.auth_denied(request, reason="admin_access_required", role=role)
        raise HTTPException(status_code=403, detail="Admin access required")
