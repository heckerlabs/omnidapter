"""Hosted connection endpoints with tenant isolation."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from omnidapter import Omnidapter
from omnidapter_server.database import get_session
from omnidapter_server.encryption import EncryptionService
from omnidapter_server.models.connection import Connection, ConnectionStatus
from omnidapter_server.schemas.connection import (
    ConnectionResponse,
    CreateConnectionRequest,
    CreateConnectionResponse,
    ReauthorizeConnectionRequest,
)
from omnidapter_server.services.connection_flows import (
    create_connection_flow,
    get_connection_or_404,
    list_connections_flow,
    reauthorize_connection_flow,
)
from omnidapter_server.services.connection_health import transition_to_revoked
from omnidapter_server.stores.credential_store import DatabaseCredentialStore
from omnidapter_server.stores.factory import build_oauth_state_store
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_hosted.config import HostedSettings, get_hosted_settings
from omnidapter_hosted.dependencies import (
    HostedAuthContext,
    get_encryption_service,
    get_hosted_auth_context,
    get_request_id,
)
from omnidapter_hosted.models.connection_owner import HostedConnectionOwner
from omnidapter_hosted.services.provider_registry import build_hosted_provider_registry
from omnidapter_hosted.services.tenant_resources import (
    enforce_fallback_connection_limit,
    get_tenant_provider_config,
)

router = APIRouter(prefix="/connections", tags=["connections"])


async def _build_omni(
    session: AsyncSession,
    encryption: EncryptionService,
    settings: HostedSettings,
    tenant_id: uuid.UUID,
    provider_key: str,
    provider_config: object | None,
) -> Omnidapter:
    cred_store = DatabaseCredentialStore(session=session, encryption=encryption)
    state_store = build_oauth_state_store(settings, session, encryption)
    registry = await build_hosted_provider_registry(
        tenant_id=tenant_id,
        provider_key=provider_key,
        session=session,
        settings=settings,
        encryption=encryption,
    )
    return Omnidapter(
        credential_store=cred_store,
        oauth_state_store=state_store,
        registry=registry,
    )


async def _persist_owner(
    conn: Connection,
    session: AsyncSession,
    tenant_id: uuid.UUID,
) -> None:
    session.add(
        HostedConnectionOwner(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            connection_id=conn.id,
        )
    )


async def _load_connection_by_uuid(
    conn_uuid: uuid.UUID,
    session: AsyncSession,
    tenant_id: uuid.UUID,
) -> Connection | None:
    result = await session.execute(
        select(Connection)
        .join(HostedConnectionOwner, HostedConnectionOwner.connection_id == Connection.id)
        .where(Connection.id == conn_uuid, HostedConnectionOwner.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def _count_active_connections(
    provider_key: str,
    session: AsyncSession,
    tenant_id: uuid.UUID,
) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(Connection)
        .join(HostedConnectionOwner, HostedConnectionOwner.connection_id == Connection.id)
        .where(
            HostedConnectionOwner.tenant_id == tenant_id,
            Connection.provider_key == provider_key,
            Connection.status != ConnectionStatus.REVOKED,
        )
    )
    return int(result.scalar_one())


async def _load_paginated_connections(
    session: AsyncSession,
    status: str | None,
    provider: str | None,
    limit: int,
    offset: int,
    external_id: str | None = None,
    *,
    tenant_id: uuid.UUID,
) -> tuple[int, list[Connection]]:
    query = (
        select(Connection)
        .join(HostedConnectionOwner, HostedConnectionOwner.connection_id == Connection.id)
        .where(HostedConnectionOwner.tenant_id == tenant_id)
    )
    if status:
        query = query.where(Connection.status == status)
    if provider:
        query = query.where(Connection.provider_key == provider)
    if external_id:
        query = query.where(Connection.external_id == external_id)

    total_result = await session.execute(select(func.count()).select_from(query.subquery()))
    total = int(total_result.scalar_one())

    result = await session.execute(query.offset(offset).limit(limit))
    return total, list(result.scalars().all())


async def _load_connection(
    connection_id: str, session: AsyncSession, tenant_id: uuid.UUID
) -> Connection:
    return await get_connection_or_404(
        connection_id=connection_id,
        session=session,
        load_connection_by_uuid=lambda conn_uuid, s: _load_connection_by_uuid(
            conn_uuid, s, tenant_id
        ),
    )


async def _get_owned_connection_or_404(
    *,
    connection_id: str,
    tenant_id: uuid.UUID,
    session: AsyncSession,
) -> Connection:
    return await _load_connection(connection_id, session, tenant_id)


@router.post("", status_code=201)
async def create_connection(
    body: CreateConnectionRequest,
    request: Request,
    auth: Annotated[HostedAuthContext, Depends(get_hosted_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: HostedSettings = Depends(get_hosted_settings),
    request_id: str = Depends(get_request_id),
):
    await enforce_fallback_connection_limit(
        session=session,
        tenant_id=auth.tenant_id,
        provider_key=body.provider,
        limit=settings.hosted_fallback_connection_limit,
    )
    flow_result = await create_connection_flow(
        body=body,
        request=request,
        session=session,
        settings=settings,
        load_provider_config=lambda provider_key, s: get_tenant_provider_config(
            session=s,
            tenant_id=auth.tenant_id,
            provider_key=provider_key,
        ),
        count_active_connections=lambda provider_key, s: _count_active_connections(
            provider_key,
            s,
            auth.tenant_id,
        ),
        build_omni=lambda s, provider_key, provider_config: _build_omni(
            s,
            encryption,
            settings,
            auth.tenant_id,
            provider_key,
            provider_config,
        ),
        persist_post_create=lambda conn, s: _persist_owner(conn, s, auth.tenant_id),
    )
    return {
        "data": CreateConnectionResponse(
            connection_id=flow_result.connection_id,
            status=flow_result.status,
            authorization_url=flow_result.authorization_url,
        ),
        "meta": {"request_id": request_id},
    }


@router.get("")
async def list_connections(
    auth: Annotated[HostedAuthContext, Depends(get_hosted_auth_context)],
    session: AsyncSession = Depends(get_session),
    request_id: str = Depends(get_request_id),
    status: str | None = Query(None),
    provider: str | None = Query(None),
    external_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    total, connections = await list_connections_flow(
        session=session,
        status=status,
        provider=provider,
        external_id=external_id,
        limit=limit,
        offset=offset,
        load_paginated_connections=lambda s, st, p, page_limit, page_offset, ext_id: (
            _load_paginated_connections(
                s,
                st,
                p,
                page_limit,
                page_offset,
                ext_id,
                tenant_id=auth.tenant_id,
            )
        ),
    )
    return {
        "data": [ConnectionResponse.from_model(c) for c in connections],
        "meta": {
            "request_id": request_id,
            "pagination": {
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < total,
            },
        },
    }


@router.get("/{connection_id}")
async def get_connection_endpoint(
    connection_id: str,
    auth: Annotated[HostedAuthContext, Depends(get_hosted_auth_context)],
    session: AsyncSession = Depends(get_session),
    request_id: str = Depends(get_request_id),
):
    conn = await _load_connection(connection_id, session, auth.tenant_id)
    return {
        "data": ConnectionResponse.from_model(conn),
        "meta": {"request_id": request_id},
    }


@router.delete("/{connection_id}", status_code=204)
async def delete_connection(
    connection_id: str,
    auth: Annotated[HostedAuthContext, Depends(get_hosted_auth_context)],
    session: AsyncSession = Depends(get_session),
):
    conn = await _load_connection(connection_id, session, auth.tenant_id)
    await transition_to_revoked(conn.id, session, reason="Deleted by API")
    # Clean up the hosted connection owner record
    await session.execute(
        delete(HostedConnectionOwner).where(HostedConnectionOwner.connection_id == conn.id)
    )
    await session.commit()


@router.post("/{connection_id}/reauthorize", status_code=200)
async def reauthorize_connection(
    connection_id: str,
    body: ReauthorizeConnectionRequest,
    request: Request,
    auth: Annotated[HostedAuthContext, Depends(get_hosted_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: HostedSettings = Depends(get_hosted_settings),
    request_id: str = Depends(get_request_id),
):
    flow_result = await reauthorize_connection_flow(
        connection_id=connection_id,
        body=body,
        request=request,
        session=session,
        settings=settings,
        load_connection=lambda conn_id, s: _load_connection(conn_id, s, auth.tenant_id),
        load_provider_config=lambda provider_key, s: get_tenant_provider_config(
            session=s,
            tenant_id=auth.tenant_id,
            provider_key=provider_key,
        ),
        build_omni=lambda s, provider_key, provider_config: _build_omni(
            s,
            encryption,
            settings,
            auth.tenant_id,
            provider_key,
            provider_config,
        ),
    )

    return {
        "data": {
            "connection_id": flow_result.connection_id,
            "status": flow_result.status,
            "authorization_url": flow_result.authorization_url,
        },
        "meta": {"request_id": request_id},
    }
