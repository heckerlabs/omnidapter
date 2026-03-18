"""Hosted FastAPI dependency injection helpers."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from omnidapter_server.config import Settings as ServerSettings
from omnidapter_server.database import get_session
from omnidapter_server.encryption import EncryptionService
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_hosted.config import HostedSettings, get_hosted_settings
from omnidapter_hosted.models.api_key import HostedAPIKey
from omnidapter_hosted.models.tenant import Tenant
from omnidapter_hosted.services.auth import authenticate_hosted_key, update_key_last_used
from omnidapter_hosted.services.billing import check_rate_limit


class HostedAuthContext:
    """Resolved authentication context for a hosted request."""

    def __init__(self, api_key: HostedAPIKey, tenant: Tenant) -> None:
        self.api_key = api_key
        self.tenant = tenant

    @property
    def tenant_id(self) -> uuid.UUID:
        return self.tenant.id

    @property
    def plan(self) -> str:
        return self.tenant.plan

    @property
    def is_test(self) -> bool:
        return self.api_key.is_test


def get_server_settings() -> ServerSettings:
    from omnidapter_server.config import get_settings

    return get_settings()


def get_encryption_service(
    settings: Annotated[ServerSettings, Depends(get_server_settings)],
) -> EncryptionService:
    return EncryptionService(
        current_key=settings.omnidapter_encryption_key,
        previous_key=settings.omnidapter_encryption_key_previous,
    )


async def get_hosted_auth_context(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    session: AsyncSession = Depends(get_session),
    hosted_settings: HostedSettings = Depends(get_hosted_settings),
) -> HostedAuthContext:
    """Authenticate hosted API key and enforce rate limits."""
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
    result = await authenticate_hosted_key(raw_key, session)

    if result is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_api_key", "message": "Invalid or inactive API key"},
        )

    api_key, tenant = result

    # Rate limiting
    allowed, limit, remaining, reset_at = await check_rate_limit(
        tenant_id=str(tenant.id),
        plan=tenant.plan,
        rate_limit_free=hosted_settings.hosted_rate_limit_free,
        rate_limit_paid=hosted_settings.hosted_rate_limit_paid,
        redis_url=hosted_settings.hosted_rate_limit_redis_url,
    )

    request.state.rate_limit = {"limit": limit, "remaining": remaining, "reset": int(reset_at)}

    if not allowed:
        import time

        raise HTTPException(
            status_code=429,
            detail={"code": "rate_limited", "message": "Rate limit exceeded"},
            headers={
                "Retry-After": str(max(1, int(reset_at - time.time()))),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(reset_at)),
            },
        )

    await update_key_last_used(api_key.id, session)
    return HostedAuthContext(api_key=api_key, tenant=tenant)


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "req_unknown")
