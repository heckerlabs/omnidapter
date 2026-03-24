"""Dashboard endpoints — authenticated via JWT Bearer token.

All routes require a valid dashboard session (issued by /v1/auth/callback).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from omnidapter_server.database import get_session
from omnidapter_server.encryption import EncryptionService
from omnidapter_server.models.connection import Connection, ConnectionStatus
from omnidapter_server.services.connection_health import transition_to_revoked
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_hosted.dependencies import (
    DashboardAuthContext,
    get_dashboard_auth_context,
    get_encryption_service,
    get_request_id,
)
from omnidapter_hosted.models.api_key import HostedAPIKey
from omnidapter_hosted.models.connection_owner import HostedConnectionOwner
from omnidapter_hosted.models.membership import MemberRole
from omnidapter_hosted.models.provider_config import HostedProviderConfig
from omnidapter_hosted.services.auth import generate_hosted_api_key
from omnidapter_hosted.services.dashboard import (
    list_members,
    remove_member,
    update_tenant_name,
    update_user_name,
)
from omnidapter_hosted.services.usage import count_monthly_usage

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


class UpdateProfileRequest(BaseModel):
    name: str


@router.get("/profile")
async def get_profile(
    auth: Annotated[DashboardAuthContext, Depends(get_dashboard_auth_context)],
    request_id: str = Depends(get_request_id),
):
    return {
        "data": {"id": str(auth.user.id), "email": auth.user.email, "name": auth.user.name},
        "meta": {"request_id": request_id},
    }


@router.patch("/profile")
async def update_profile(
    body: UpdateProfileRequest,
    auth: Annotated[DashboardAuthContext, Depends(get_dashboard_auth_context)],
    session: AsyncSession = Depends(get_session),
    request_id: str = Depends(get_request_id),
):
    user = await update_user_name(auth.user, body.name.strip(), session)
    return {
        "data": {"id": str(user.id), "email": user.email, "name": user.name},
        "meta": {"request_id": request_id},
    }


# ---------------------------------------------------------------------------
# Tenant
# ---------------------------------------------------------------------------


class UpdateTenantRequest(BaseModel):
    name: str


@router.get("/tenant")
async def get_tenant(
    auth: Annotated[DashboardAuthContext, Depends(get_dashboard_auth_context)],
    request_id: str = Depends(get_request_id),
):
    t = auth.tenant
    return {
        "data": {"id": str(t.id), "name": t.name, "plan": t.plan},
        "meta": {"request_id": request_id},
    }


@router.patch("/tenant")
async def update_tenant(
    body: UpdateTenantRequest,
    auth: Annotated[DashboardAuthContext, Depends(get_dashboard_auth_context)],
    session: AsyncSession = Depends(get_session),
    request_id: str = Depends(get_request_id),
):
    tenant = await update_tenant_name(auth.tenant, body.name.strip(), auth.role, session)
    return {
        "data": {"id": str(tenant.id), "name": tenant.name, "plan": tenant.plan},
        "meta": {"request_id": request_id},
    }


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------


@router.get("/members")
async def get_members(
    auth: Annotated[DashboardAuthContext, Depends(get_dashboard_auth_context)],
    session: AsyncSession = Depends(get_session),
    request_id: str = Depends(get_request_id),
):
    rows = await list_members(auth.tenant_id, session)
    data = [
        {
            "user": {"id": str(u.id), "email": u.email, "name": u.name},
            "role": m.role,
            "joined_at": m.created_at.isoformat(),
        }
        for m, u in rows
    ]
    return {"data": data, "meta": {"request_id": request_id}}


@router.delete("/members/{user_id}", status_code=204)
async def delete_member(
    user_id: str,
    auth: Annotated[DashboardAuthContext, Depends(get_dashboard_auth_context)],
    session: AsyncSession = Depends(get_session),
):
    try:
        target_user_id = uuid.UUID(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Member not found"}) from exc

    await remove_member(
        tenant_id=auth.tenant_id,
        target_user_id=target_user_id,
        requesting_role=auth.role,
        requesting_user_id=auth.user.id,
        session=session,
    )


# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------


class APIKeyResponse(BaseModel):
    id: str
    name: str
    key_prefix: str
    is_active: bool
    last_used_at: str | None
    created_at: str

    @classmethod
    def from_model(cls, k: HostedAPIKey) -> APIKeyResponse:
        return cls(
            id=str(k.id),
            name=k.name,
            key_prefix=k.key_prefix,
            is_active=k.is_active,
            last_used_at=k.last_used_at.isoformat() if k.last_used_at else None,
            created_at=k.created_at.isoformat(),
        )


class CreateAPIKeyRequest(BaseModel):
    name: str


@router.get("/api-keys")
async def list_api_keys(
    auth: Annotated[DashboardAuthContext, Depends(get_dashboard_auth_context)],
    session: AsyncSession = Depends(get_session),
    request_id: str = Depends(get_request_id),
):
    result = await session.execute(
        select(HostedAPIKey).where(HostedAPIKey.tenant_id == auth.tenant_id)
    )
    keys = result.scalars().all()
    return {
        "data": [APIKeyResponse.from_model(k) for k in keys],
        "meta": {"request_id": request_id},
    }


@router.post("/api-keys", status_code=201)
async def create_api_key(
    body: CreateAPIKeyRequest,
    auth: Annotated[DashboardAuthContext, Depends(get_dashboard_auth_context)],
    session: AsyncSession = Depends(get_session),
    request_id: str = Depends(get_request_id),
):
    if auth.role not in (MemberRole.OWNER, MemberRole.ADMIN):
        raise HTTPException(
            status_code=403,
            detail={"code": "forbidden", "message": "Owner or admin role required"},
        )

    raw_key, key_hash, key_prefix = generate_hosted_api_key()
    api_key = HostedAPIKey(
        id=uuid.uuid4(),
        tenant_id=auth.tenant_id,
        name=body.name.strip(),
        key_hash=key_hash,
        key_prefix=key_prefix,
        is_active=True,
    )
    session.add(api_key)
    await session.commit()
    await session.refresh(api_key)

    response_data = APIKeyResponse.from_model(api_key).model_dump()
    response_data["key"] = raw_key
    return {"data": response_data, "meta": {"request_id": request_id}}


@router.delete("/api-keys/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: str,
    auth: Annotated[DashboardAuthContext, Depends(get_dashboard_auth_context)],
    session: AsyncSession = Depends(get_session),
):
    if auth.role not in (MemberRole.OWNER, MemberRole.ADMIN):
        raise HTTPException(
            status_code=403,
            detail={"code": "forbidden", "message": "Owner or admin role required"},
        )

    try:
        key_uuid = uuid.UUID(key_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "API key not found"}) from exc

    result = await session.execute(
        select(HostedAPIKey).where(
            HostedAPIKey.id == key_uuid,
            HostedAPIKey.tenant_id == auth.tenant_id,
        )
    )
    key = result.scalar_one_or_none()
    if key is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "API key not found"})

    await session.execute(
        update(HostedAPIKey).where(HostedAPIKey.id == key_uuid).values(is_active=False)
    )
    await session.commit()


# ---------------------------------------------------------------------------
# Connections (read-only view + force-revoke)
# ---------------------------------------------------------------------------


@router.get("/connections")
async def list_connections(
    auth: Annotated[DashboardAuthContext, Depends(get_dashboard_auth_context)],
    session: AsyncSession = Depends(get_session),
    request_id: str = Depends(get_request_id),
):
    result = await session.execute(
        select(Connection)
        .join(HostedConnectionOwner, HostedConnectionOwner.connection_id == Connection.id)
        .where(HostedConnectionOwner.tenant_id == auth.tenant_id)
        .where(Connection.status != ConnectionStatus.REVOKED)
        .order_by(Connection.created_at.desc())
    )
    connections = result.scalars().all()

    data = [
        {
            "id": str(c.id),
            "provider_key": c.provider_key,
            "status": c.status,
            "external_id": c.external_id,
            "last_used_at": c.last_used_at.isoformat() if c.last_used_at else None,
            "created_at": c.created_at.isoformat(),
        }
        for c in connections
    ]
    return {"data": data, "meta": {"request_id": request_id}}


@router.delete("/connections/{connection_id}", status_code=204)
async def revoke_connection(
    connection_id: str,
    auth: Annotated[DashboardAuthContext, Depends(get_dashboard_auth_context)],
    session: AsyncSession = Depends(get_session),
):
    if auth.role not in (MemberRole.OWNER, MemberRole.ADMIN):
        raise HTTPException(
            status_code=403,
            detail={"code": "forbidden", "message": "Owner or admin role required"},
        )

    try:
        conn_uuid = uuid.UUID(connection_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Connection not found"}) from exc

    result = await session.execute(
        select(Connection)
        .join(HostedConnectionOwner, HostedConnectionOwner.connection_id == Connection.id)
        .where(Connection.id == conn_uuid, HostedConnectionOwner.tenant_id == auth.tenant_id)
    )
    conn = result.scalar_one_or_none()
    if conn is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Connection not found"})

    await transition_to_revoked(conn.id, session, reason="Revoked from dashboard")


# ---------------------------------------------------------------------------
# Provider Configs
# ---------------------------------------------------------------------------


class UpsertProviderConfigRequest(BaseModel):
    client_id: str
    client_secret: str
    scopes: list[str] | None = None


@router.get("/provider-configs")
async def list_provider_configs(
    auth: Annotated[DashboardAuthContext, Depends(get_dashboard_auth_context)],
    session: AsyncSession = Depends(get_session),
    request_id: str = Depends(get_request_id),
):
    result = await session.execute(
        select(HostedProviderConfig).where(HostedProviderConfig.tenant_id == auth.tenant_id)
    )
    configs = result.scalars().all()

    data = [
        {
            "provider_key": c.provider_key,
            "auth_kind": c.auth_kind,
            "scopes": c.scopes,
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
        }
        for c in configs
    ]
    return {"data": data, "meta": {"request_id": request_id}}


@router.put("/provider-configs/{provider_key}", status_code=200)
async def upsert_provider_config(
    provider_key: str,
    body: UpsertProviderConfigRequest,
    auth: Annotated[DashboardAuthContext, Depends(get_dashboard_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    request_id: str = Depends(get_request_id),
):
    if auth.role not in (MemberRole.OWNER, MemberRole.ADMIN):
        raise HTTPException(
            status_code=403,
            detail={"code": "forbidden", "message": "Owner or admin role required"},
        )

    result = await session.execute(
        select(HostedProviderConfig).where(
            HostedProviderConfig.tenant_id == auth.tenant_id,
            HostedProviderConfig.provider_key == provider_key,
        )
    )
    config = result.scalar_one_or_none()

    encrypted_id = encryption.encrypt(body.client_id)
    encrypted_secret = encryption.encrypt(body.client_secret)

    if config is None:
        config = HostedProviderConfig(
            id=uuid.uuid4(),
            tenant_id=auth.tenant_id,
            provider_key=provider_key,
            auth_kind="oauth2",
            client_id_encrypted=encrypted_id,
            client_secret_encrypted=encrypted_secret,
            scopes=body.scopes,
        )
        session.add(config)
    else:
        config.client_id_encrypted = encrypted_id
        config.client_secret_encrypted = encrypted_secret
        config.scopes = body.scopes

    await session.commit()
    await session.refresh(config)

    return {
        "data": {
            "provider_key": config.provider_key,
            "auth_kind": config.auth_kind,
            "scopes": config.scopes,
            "updated_at": config.updated_at.isoformat(),
        },
        "meta": {"request_id": request_id},
    }


@router.delete("/provider-configs/{provider_key}", status_code=204)
async def delete_provider_config(
    provider_key: str,
    auth: Annotated[DashboardAuthContext, Depends(get_dashboard_auth_context)],
    session: AsyncSession = Depends(get_session),
):
    if auth.role not in (MemberRole.OWNER, MemberRole.ADMIN):
        raise HTTPException(
            status_code=403,
            detail={"code": "forbidden", "message": "Owner or admin role required"},
        )

    result = await session.execute(
        select(HostedProviderConfig).where(
            HostedProviderConfig.tenant_id == auth.tenant_id,
            HostedProviderConfig.provider_key == provider_key,
        )
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "Provider config not found"},
        )

    await session.delete(config)
    await session.commit()


# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------


@router.get("/usage")
async def get_usage(
    auth: Annotated[DashboardAuthContext, Depends(get_dashboard_auth_context)],
    session: AsyncSession = Depends(get_session),
    request_id: str = Depends(get_request_id),
):
    from omnidapter_hosted.config import get_hosted_settings

    settings = get_hosted_settings()
    calls_this_month = await count_monthly_usage(auth.tenant_id, session)

    limit = None if auth.tenant.plan != "free" else settings.hosted_free_tier_calls

    return {
        "data": {
            "plan": auth.tenant.plan,
            "calls_this_month": calls_this_month,
            "limit": limit,
        },
        "meta": {"request_id": request_id},
    }
