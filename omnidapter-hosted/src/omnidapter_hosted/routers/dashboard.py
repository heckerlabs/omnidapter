"""Dashboard endpoints — authenticated via JWT Bearer token."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from omnidapter_server.database import get_session
from omnidapter_server.encryption import EncryptionService
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_hosted.dependencies import (
    DashboardAuthContext,
    get_dashboard_auth_context,
    get_encryption_service,
    get_request_id,
)
from omnidapter_hosted.models.api_key import HostedAPIKey
from omnidapter_hosted.services.dashboard import (
    create_api_key_flow,
    delete_provider_config_flow,
    list_api_keys_flow,
    list_connections_flow,
    list_members,
    list_provider_configs_flow,
    remove_member,
    revoke_api_key_flow,
    revoke_connection_flow,
    update_tenant_name,
    update_user_name,
    upsert_provider_config_flow,
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
async def patch_tenant(
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
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "Member not found"}
        ) from exc

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


def _api_key_data(k: HostedAPIKey) -> dict:
    return {
        "id": str(k.id),
        "name": k.name,
        "key_prefix": k.key_prefix,
        "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
        "created_at": k.created_at.isoformat(),
    }


class CreateAPIKeyRequest(BaseModel):
    name: str


@router.get("/api-keys")
async def list_api_keys(
    auth: Annotated[DashboardAuthContext, Depends(get_dashboard_auth_context)],
    session: AsyncSession = Depends(get_session),
    request_id: str = Depends(get_request_id),
):
    keys = await list_api_keys_flow(auth.tenant_id, session)
    return {"data": [_api_key_data(k) for k in keys], "meta": {"request_id": request_id}}


@router.post("/api-keys", status_code=201)
async def create_api_key(
    body: CreateAPIKeyRequest,
    auth: Annotated[DashboardAuthContext, Depends(get_dashboard_auth_context)],
    session: AsyncSession = Depends(get_session),
    request_id: str = Depends(get_request_id),
):
    raw_key, api_key = await create_api_key_flow(
        auth.tenant_id, body.name.strip(), auth.role, session
    )
    data = _api_key_data(api_key)
    data["key"] = raw_key
    return {"data": data, "meta": {"request_id": request_id}}


@router.delete("/api-keys/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: str,
    auth: Annotated[DashboardAuthContext, Depends(get_dashboard_auth_context)],
    session: AsyncSession = Depends(get_session),
):
    try:
        key_uuid = uuid.UUID(key_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "API key not found"}
        ) from exc

    await revoke_api_key_flow(key_uuid, auth.tenant_id, auth.role, session)


# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------


@router.get("/connections")
async def list_connections(
    auth: Annotated[DashboardAuthContext, Depends(get_dashboard_auth_context)],
    session: AsyncSession = Depends(get_session),
    request_id: str = Depends(get_request_id),
):
    connections = await list_connections_flow(auth.tenant_id, session)
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
    try:
        conn_uuid = uuid.UUID(connection_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "Connection not found"}
        ) from exc

    await revoke_connection_flow(conn_uuid, auth.tenant_id, auth.role, session)


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
    configs = await list_provider_configs_flow(auth.tenant_id, session)
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


@router.put("/provider-configs/{provider_key}")
async def upsert_provider_config(
    provider_key: str,
    body: UpsertProviderConfigRequest,
    auth: Annotated[DashboardAuthContext, Depends(get_dashboard_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    request_id: str = Depends(get_request_id),
):
    config = await upsert_provider_config_flow(
        tenant_id=auth.tenant_id,
        provider_key=provider_key,
        client_id=body.client_id,
        client_secret=body.client_secret,
        scopes=body.scopes,
        role=auth.role,
        encryption=encryption,
        session=session,
    )
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
    await delete_provider_config_flow(auth.tenant_id, provider_key, auth.role, session)


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
        "data": {"plan": auth.tenant.plan, "calls_this_month": calls_this_month, "limit": limit},
        "meta": {"request_id": request_id},
    }
