"""WorkOS AuthKit endpoints — login, callback, me, and logout.

Uses stateless JWT Bearer tokens instead of session cookies.
"""

from __future__ import annotations

import logging
import secrets
import uuid

import jwt
from fastapi import APIRouter, Depends, HTTPException
from omnidapter_server.database import get_session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from workos import AsyncWorkOSClient

from omnidapter_hosted.config import HostedSettings, get_hosted_settings
from omnidapter_hosted.dependencies import (
    DashboardAuthContext,
    get_dashboard_auth_context,
    get_request_id,
)
from omnidapter_hosted.models.api_key import HostedAPIKey
from omnidapter_hosted.models.membership import HostedMembership, MemberRole
from omnidapter_hosted.models.tenant import Tenant
from omnidapter_hosted.models.user import HostedUser
from omnidapter_hosted.services.auth import generate_hosted_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Module-level fallback secret — replaced by JWT_SECRET env var in production.
# Rotates on restart if env var is not set; warn loudly.
_fallback_jwt_secret: str | None = None


def _get_jwt_secret(settings: HostedSettings) -> str:
    global _fallback_jwt_secret
    if settings.jwt_secret:
        return settings.jwt_secret
    if _fallback_jwt_secret is None:
        _fallback_jwt_secret = secrets.token_hex(32)
        logger.warning(
            "JWT_SECRET is not configured — using a randomly generated secret. "
            "Dashboard sessions will be invalidated on restart. Set JWT_SECRET in production."
        )
    return _fallback_jwt_secret


def _workos_client(settings: HostedSettings) -> AsyncWorkOSClient:
    return AsyncWorkOSClient(
        api_key=settings.workos_api_key,
        client_id=settings.workos_client_id,
    )


def _require_workos(settings: HostedSettings) -> None:
    if not settings.workos_api_key or not settings.workos_client_id:
        raise HTTPException(
            status_code=503,
            detail={"code": "workos_not_configured", "message": "WorkOS is not configured"},
        )


def _issue_jwt(
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    role: str,
    settings: HostedSettings,
) -> str:
    import time

    secret = _get_jwt_secret(settings)
    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + settings.jwt_ttl_seconds,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


async def _get_or_provision_user(
    workos_user_id: str,
    email: str,
    first_name: str | None,
    last_name: str | None,
    session: AsyncSession,
) -> tuple[HostedUser, Tenant, HostedMembership, HostedAPIKey | None]:
    """Return (user, tenant, membership, initial_api_key).

    initial_api_key is only non-None on the very first signup.
    """
    result = await session.execute(
        select(HostedUser).where(HostedUser.workos_user_id == workos_user_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        result = await session.execute(select(HostedUser).where(HostedUser.email == email))
        user = result.scalar_one_or_none()
        if user is not None:
            user.workos_user_id = workos_user_id
            await session.flush()

    if user is not None:
        result = await session.execute(
            select(HostedMembership)
            .where(HostedMembership.user_id == user.id)
            .where(HostedMembership.role == MemberRole.OWNER)
        )
        membership = result.scalar_one_or_none()
        if membership is None:
            result = await session.execute(
                select(HostedMembership).where(HostedMembership.user_id == user.id)
            )
            membership = result.scalar_one_or_none()

        if membership is None:
            raise HTTPException(
                status_code=500,
                detail={"code": "no_membership", "message": "User has no membership"},
            )

        tenant_result = await session.execute(
            select(Tenant).where(Tenant.id == membership.tenant_id)
        )
        tenant = tenant_result.scalar_one()
        return user, tenant, membership, None

    # --- First sign-in: provision user + tenant + membership + initial API key ---
    name = " ".join(filter(None, [first_name, last_name])) or email.split("@")[0]

    user = HostedUser(id=uuid.uuid4(), email=email, name=name, workos_user_id=workos_user_id)
    session.add(user)
    await session.flush()

    tenant = Tenant(id=uuid.uuid4(), name=name, is_active=True)
    session.add(tenant)
    await session.flush()

    membership = HostedMembership(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        user_id=user.id,
        role=MemberRole.OWNER,
    )
    session.add(membership)
    await session.flush()

    raw_key, key_hash, key_prefix = generate_hosted_api_key()
    api_key = HostedAPIKey(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name="default",
        key_hash=key_hash,
        key_prefix=key_prefix,
        is_active=True,
    )
    session.add(api_key)
    await session.commit()
    await session.refresh(user)
    await session.refresh(tenant)
    api_key.raw_key = raw_key  # type: ignore[attr-defined]

    logger.info("Provisioned new user %s with tenant %s", user.id, tenant.id)
    return user, tenant, membership, api_key


@router.get("/login")
async def login(
    redirect_uri: str | None = None,
    settings: HostedSettings = Depends(get_hosted_settings),
):
    """Return the WorkOS AuthKit authorization URL."""
    _require_workos(settings)
    client = _workos_client(settings)
    callback_uri = redirect_uri or f"{settings.omnidapter_base_url}/v1/auth/callback"
    url = client.user_management.get_authorization_url(
        redirect_uri=callback_uri,
        provider="authkit",
    )
    return {"url": url}


@router.get("/callback")
async def callback(
    code: str,
    session: AsyncSession = Depends(get_session),
    settings: HostedSettings = Depends(get_hosted_settings),
    request_id: str = Depends(get_request_id),
):
    """Exchange the WorkOS authorization code for a JWT access token.

    Returns the raw API key only on first signup.
    """
    _require_workos(settings)
    client = _workos_client(settings)

    auth_response = await client.user_management.authenticate_with_code(code=code)
    wu = auth_response.user

    user, tenant, membership, initial_key = await _get_or_provision_user(
        workos_user_id=wu.id,
        email=wu.email,
        first_name=wu.first_name,
        last_name=wu.last_name,
        session=session,
    )

    access_token = _issue_jwt(user.id, tenant.id, membership.role, settings)

    data: dict = {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {"id": str(user.id), "email": user.email, "name": user.name},
        "tenant": {"id": str(tenant.id), "name": tenant.name, "plan": tenant.plan},
    }
    if initial_key is not None:
        data["api_key"] = getattr(initial_key, "raw_key", None)

    return {"data": data, "meta": {"request_id": request_id}}


@router.get("/me")
async def me(
    auth: DashboardAuthContext = Depends(get_dashboard_auth_context),
    request_id: str = Depends(get_request_id),
):
    """Return the currently authenticated user and tenant."""
    return {
        "data": {
            "user": {"id": str(auth.user.id), "email": auth.user.email, "name": auth.user.name},
            "tenant": {
                "id": str(auth.tenant.id),
                "name": auth.tenant.name,
                "plan": auth.tenant.plan,
            },
            "role": auth.membership.role,
        },
        "meta": {"request_id": request_id},
    }


@router.post("/logout")
async def logout(request_id: str = Depends(get_request_id)):
    """Stateless logout — client discards the Bearer token."""
    return {"data": {"logged_out": True}, "meta": {"request_id": request_id}}
