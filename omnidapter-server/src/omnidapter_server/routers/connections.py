"""Connection management endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from omnidapter import Omnidapter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_server.config import Settings, get_settings
from omnidapter_server.database import get_session
from omnidapter_server.dependencies import (
    AuthContext,
    get_auth_context,
    get_encryption_service,
    get_request_id,
)
from omnidapter_server.encryption import EncryptionService
from omnidapter_server.models.connection import Connection, ConnectionStatus
from omnidapter_server.provider_registry import build_provider_registry
from omnidapter_server.schemas.common import ApiResponse, ListResponse
from omnidapter_server.schemas.connection import (
    ConnectionResponse,
    CreateConnectionRequest,
    CreateConnectionResponse,
    ReauthorizeConnectionRequest,
    ReauthorizeConnectionResponse,
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

router = APIRouter(prefix="/connections", tags=["connections"])


async def _build_omni(
    session: AsyncSession,
    encryption: EncryptionService,
    settings: Settings,
    provider_key: str,
) -> Omnidapter:
    cred_store = DatabaseCredentialStore(session=session, encryption=encryption)
    state_store = build_oauth_state_store(settings, session, encryption)
    registry = build_provider_registry(settings)

    return Omnidapter(
        credential_store=cred_store,
        oauth_state_store=state_store,
        registry=registry,
    )


async def _load_connection_by_uuid(
    conn_uuid: uuid.UUID, session: AsyncSession
) -> Connection | None:
    result = await session.execute(select(Connection).where(Connection.id == conn_uuid))
    return result.scalar_one_or_none()


async def _count_active_connections(provider_key: str, session: AsyncSession) -> int:
    result = await session.execute(
        select(func.count()).where(
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
) -> tuple[int, list[Connection]]:
    query = select(Connection)
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


async def get_connection(
    connection_id: str,
    session: AsyncSession,
) -> Connection:
    """Fetch a connection by ID. Raises 404 if not found."""
    return await get_connection_or_404(
        connection_id=connection_id,
        session=session,
        load_connection_by_uuid=_load_connection_by_uuid,
    )


@router.post("", status_code=201, operation_id="create_connection", response_model=ApiResponse[CreateConnectionResponse])
async def create_connection(
    body: CreateConnectionRequest,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
):
    """Create a new connection and begin the OAuth flow."""
    flow_result = await create_connection_flow(
        body=body,
        request=request,
        session=session,
        settings=settings,
        count_active_connections=_count_active_connections,
        build_omni=lambda s, provider_key, provider_config: _build_omni(
            s,
            encryption,
            settings,
            provider_key,
        ),
    )
    return {
        "data": CreateConnectionResponse(
            connection_id=flow_result.connection_id,
            status=flow_result.status,
            authorization_url=flow_result.authorization_url,
        ),
        "meta": {"request_id": request_id},
    }


@router.get("", operation_id="list_connections", response_model=ListResponse[ConnectionResponse])
async def list_connections(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
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
        load_paginated_connections=_load_paginated_connections,
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


@router.get("/{connection_id}", operation_id="get_connection", response_model=ApiResponse[ConnectionResponse])
async def get_connection_endpoint(
    connection_id: str,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: AsyncSession = Depends(get_session),
    request_id: str = Depends(get_request_id),
):
    conn = await get_connection(connection_id, session)
    return {
        "data": ConnectionResponse.from_model(conn),
        "meta": {"request_id": request_id},
    }


@router.delete("/{connection_id}", status_code=204, operation_id="delete_connection")
async def delete_connection(
    connection_id: str,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: AsyncSession = Depends(get_session),
):
    conn = await get_connection(connection_id, session)
    await transition_to_revoked(conn.id, session, reason="Deleted by API")


@router.post("/{connection_id}/reauthorize", status_code=200, operation_id="reauthorize_connection", response_model=ApiResponse[ReauthorizeConnectionResponse])
async def reauthorize_connection(
    connection_id: str,
    body: ReauthorizeConnectionRequest,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
):
    flow_result = await reauthorize_connection_flow(
        connection_id=connection_id,
        body=body,
        request=request,
        session=session,
        settings=settings,
        load_connection=get_connection,
        build_omni=lambda s, provider_key, provider_config: _build_omni(
            s,
            encryption,
            settings,
            provider_key,
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
