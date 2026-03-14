"""FastAPI dependency injection helpers."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_api.config import Settings, get_settings
from omnidapter_api.database import get_session
from omnidapter_api.encryption import EncryptionService
from omnidapter_api.models.api_key import APIKey
from omnidapter_api.models.organization import Organization
from omnidapter_api.services.auth import authenticate_api_key, update_last_used
from omnidapter_api.services.rate_limit import check_rate_limit


def get_encryption_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> EncryptionService:
    return EncryptionService(
        current_key=settings.omnidapter_encryption_key,
        previous_key=settings.omnidapter_encryption_key_previous,
    )


class AuthContext:
    """Resolved authentication context for a request."""

    def __init__(self, api_key: APIKey, organization: Organization) -> None:
        self.api_key = api_key
        self.organization = organization

    @property
    def org_id(self):
        return self.organization.id

    @property
    def plan(self):
        return self.organization.plan


async def get_auth_context(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AuthContext:
    """Extract and validate API key from Authorization header."""
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_api_key", "message": "Missing Authorization header"},
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={
                "code": "invalid_api_key",
                "message": "Authorization header must be 'Bearer <key>'",
            },
        )

    raw_key = authorization[7:]
    result = await authenticate_api_key(raw_key, session)

    if result is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_api_key", "message": "Invalid or inactive API key"},
        )

    api_key, org = result

    # Check rate limits
    allowed, limit, remaining, reset_at = check_rate_limit(
        org_id=str(org.id),
        plan=org.plan,
        rate_limit_free=settings.omnidapter_rate_limit_free,
        rate_limit_paid=settings.omnidapter_rate_limit_paid,
    )

    # Attach rate limit headers to request state for response headers
    request.state.rate_limit = {"limit": limit, "remaining": remaining, "reset": int(reset_at)}

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={"code": "rate_limited", "message": "Rate limit exceeded"},
            headers={
                "Retry-After": str(max(1, int(reset_at - __import__("time").time()))),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(reset_at)),
            },
        )

    # Update last_used_at asynchronously (don't await, fire and forget)
    await update_last_used(api_key.id, session)

    return AuthContext(api_key=api_key, organization=org)


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "req_unknown")
