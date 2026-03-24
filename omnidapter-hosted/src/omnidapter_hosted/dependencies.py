"""Hosted FastAPI dependency injection helpers."""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from omnidapter_server.config import Settings as ServerSettings
from omnidapter_server.database import get_session
from omnidapter_server.encryption import EncryptionService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_hosted.config import HostedSettings, get_hosted_settings
from omnidapter_hosted.models.api_key import HostedAPIKey
from omnidapter_hosted.models.membership import HostedMembership
from omnidapter_hosted.models.tenant import Tenant
from omnidapter_hosted.models.user import HostedUser
from omnidapter_hosted.services.auth import authenticate_hosted_key, update_key_last_used
from omnidapter_hosted.services.billing import check_rate_limit

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="BearerAuth",
    description="Use `Authorization: Bearer <API_KEY>`",
)


# ---------------------------------------------------------------------------
# Integration API auth — omni_* API key
# ---------------------------------------------------------------------------


class HostedAuthContext:
    """Resolved authentication context for a hosted API key request."""

    def __init__(self, api_key: HostedAPIKey, tenant: Tenant) -> None:
        self.api_key = api_key
        self.tenant = tenant

    @property
    def tenant_id(self) -> uuid.UUID:
        return self.tenant.id

    @property
    def plan(self) -> str:
        return self.tenant.plan


async def get_hosted_auth_context(
    request: Request,
    bearer_credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(_bearer_scheme),
    ] = None,
    session: AsyncSession = Depends(get_session),
    hosted_settings: HostedSettings = Depends(get_hosted_settings),
) -> HostedAuthContext:
    """Authenticate hosted API key and enforce rate limits."""
    if not request.headers.get("Authorization"):
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_api_key", "message": "Missing Authorization header"},
        )

    if bearer_credentials is None:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "invalid_api_key",
                "message": "Authorization header must be 'Bearer <key>'",
            },
        )

    raw_key = bearer_credentials.credentials
    result = await authenticate_hosted_key(raw_key, session)

    if result is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_api_key", "message": "Invalid or inactive API key"},
        )

    api_key, tenant = result

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


# ---------------------------------------------------------------------------
# Dashboard auth — JWT Bearer token issued by /v1/auth/callback
# ---------------------------------------------------------------------------


class DashboardAuthContext:
    """Resolved authentication context for a dashboard (JWT) request."""

    def __init__(self, user: HostedUser, tenant: Tenant, membership: HostedMembership) -> None:
        self.user = user
        self.tenant = tenant
        self.membership = membership

    @property
    def tenant_id(self) -> uuid.UUID:
        return self.tenant.id

    @property
    def role(self) -> str:
        return self.membership.role


async def get_dashboard_auth_context(
    bearer_credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(_bearer_scheme),
    ] = None,
    session: AsyncSession = Depends(get_session),
    settings: HostedSettings = Depends(get_hosted_settings),
) -> DashboardAuthContext:
    """Validate a JWT Bearer token and return the dashboard auth context."""
    if bearer_credentials is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "unauthenticated", "message": "Missing Authorization header"},
        )

    token = bearer_credentials.credentials

    # Resolve the JWT secret (same logic as auth router)
    from omnidapter_hosted.routers.auth import _get_jwt_secret

    secret = _get_jwt_secret(settings)

    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail={"code": "token_expired", "message": "Session expired — please log in again"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_token", "message": "Invalid session token"},
        )

    user_id_str = payload.get("sub")
    tenant_id_str = payload.get("tenant_id")
    if not user_id_str or not tenant_id_str:
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_token", "message": "Invalid session token"},
        )

    try:
        user_id = uuid.UUID(user_id_str)
        tenant_id = uuid.UUID(tenant_id_str)
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_token", "message": "Invalid session token"},
        )

    user_result = await session.execute(select(HostedUser).where(HostedUser.id == user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "user_not_found", "message": "User not found"},
        )

    tenant_result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = tenant_result.scalar_one_or_none()
    if tenant is None or not tenant.is_active:
        raise HTTPException(
            status_code=401,
            detail={"code": "tenant_not_found", "message": "Tenant not found or inactive"},
        )

    membership_result = await session.execute(
        select(HostedMembership)
        .where(HostedMembership.user_id == user_id)
        .where(HostedMembership.tenant_id == tenant_id)
    )
    membership = membership_result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(
            status_code=403,
            detail={"code": "forbidden", "message": "Not a member of this tenant"},
        )

    return DashboardAuthContext(user=user, tenant=tenant, membership=membership)


# ---------------------------------------------------------------------------
# Connect UI auth — lt_* link token
# ---------------------------------------------------------------------------


class LinkTokenContext:
    """Resolved context for a Connect UI request authenticated by a link token."""

    def __init__(
        self,
        tenant_id: uuid.UUID,
        end_user_id: str | None,
        allowed_providers: list[str] | None,
        redirect_uri: str | None,
    ) -> None:
        self.tenant_id = tenant_id
        self.end_user_id = end_user_id
        self.allowed_providers = allowed_providers
        self.redirect_uri = redirect_uri


async def get_link_token_context(
    bearer_credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(_bearer_scheme),
    ] = None,
    session: AsyncSession = Depends(get_session),
) -> LinkTokenContext:
    """Validate a link token and return the connect context."""
    if bearer_credentials is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "unauthenticated", "message": "Missing Authorization header"},
        )

    raw_token = bearer_credentials.credentials
    if not raw_token.startswith("lt_"):
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_token", "message": "Invalid link token"},
        )

    from omnidapter_hosted.services.link_tokens import verify_link_token

    link_token = await verify_link_token(raw_token, session)
    if link_token is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_token", "message": "Invalid or expired link token"},
        )

    return LinkTokenContext(
        tenant_id=link_token.tenant_id,
        end_user_id=link_token.end_user_id,
        allowed_providers=link_token.allowed_providers,
        redirect_uri=link_token.redirect_uri,
    )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def get_server_settings() -> ServerSettings:
    return get_hosted_settings()


def get_encryption_service(
    settings: Annotated[ServerSettings, Depends(get_server_settings)],
) -> EncryptionService:
    return EncryptionService(
        current_key=settings.omnidapter_encryption_key,
        previous_key=settings.omnidapter_encryption_key_previous,
        allow_plaintext_fallback=settings.omnidapter_env == "LOCAL",
    )


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "req_unknown")
