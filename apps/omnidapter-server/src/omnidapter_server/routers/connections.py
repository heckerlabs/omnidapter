"""Connection management endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from omnidapter import Omnidapter
from sqlalchemy import select
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
from omnidapter_server.models.provider_config import ProviderConfig
from omnidapter_server.origin_policy import parse_allowed_origin_domains, validate_redirect_url
from omnidapter_server.provider_registry import build_provider_registry
from omnidapter_server.schemas.connection import (
    ConnectionResponse,
    CreateConnectionRequest,
    CreateConnectionResponse,
    ReauthorizeConnectionRequest,
)
from omnidapter_server.services.connection_health import transition_to_revoked
from omnidapter_server.stores.credential_store import DatabaseCredentialStore
from omnidapter_server.stores.factory import build_oauth_state_store

router = APIRouter(prefix="/connections", tags=["connections"])


def _build_omni(
    session: AsyncSession,
    encryption: EncryptionService,
    settings: Settings,
    provider_config: ProviderConfig | None = None,
) -> Omnidapter:
    cred_store = DatabaseCredentialStore(session=session, encryption=encryption)
    state_store = build_oauth_state_store(settings, session, encryption)
    registry = build_provider_registry(
        settings,
        provider_config=provider_config,
        encryption=encryption,
    )

    return Omnidapter(
        credential_store=cred_store,
        oauth_state_store=state_store,
        registry=registry,
    )


async def _get_provider_config(
    provider_key: str,
    session: AsyncSession,
) -> ProviderConfig | None:
    result = await session.execute(
        select(ProviderConfig).where(ProviderConfig.provider_key == provider_key)
    )
    return result.scalar_one_or_none()


async def get_connection(
    connection_id: str,
    session: AsyncSession,
) -> Connection:
    """Fetch a connection by ID. Raises 404 if not found."""
    try:
        conn_uuid = uuid.UUID(connection_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "connection_not_found", "message": "Connection not found"},
        ) from exc

    result = await session.execute(select(Connection).where(Connection.id == conn_uuid))
    conn = result.scalar_one_or_none()
    if conn is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "connection_not_found", "message": "Connection not found"},
        )
    return conn


def _validate_redirect_url_or_422(
    redirect_url: str,
    request: Request,
    settings: Settings,
) -> None:
    allowed_domains = parse_allowed_origin_domains(settings.omnidapter_allowed_origin_domains)
    try:
        validate_redirect_url(
            redirect_url,
            request_host=request.url.hostname,
            allowed_domain_patterns=allowed_domains,
            env=settings.omnidapter_env,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_redirect_url", "message": str(exc)},
        ) from exc


@router.post("", status_code=201)
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
    _validate_redirect_url_or_422(body.redirect_url, request, settings)

    provider_config = await _get_provider_config(body.provider, session)

    # Enforce fallback connection limit when using the server's own OAuth app
    if provider_config is None or provider_config.is_fallback:
        result = await session.execute(
            select(Connection).where(
                Connection.provider_key == body.provider,
                Connection.status != ConnectionStatus.REVOKED,
            )
        )
        existing = result.scalars().all()
        if len(existing) >= settings.omnidapter_fallback_connection_limit:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "fallback_connection_limit",
                    "message": (
                        f"Fallback connection limit "
                        f"({settings.omnidapter_fallback_connection_limit}) reached. "
                        "Configure your own OAuth app via /v1/provider-configs."
                    ),
                },
            )

    conn = Connection(
        id=uuid.uuid4(),
        provider_key=body.provider,
        external_id=body.external_id,
        status=ConnectionStatus.PENDING,
        provider_config=None,
    )
    session.add(conn)
    await session.commit()
    await session.refresh(conn)

    omni = _build_omni(session, encryption, settings, provider_config)
    callback_url = f"{settings.omnidapter_base_url}/oauth/{body.provider}/callback"

    try:
        result = await omni.oauth.begin(
            provider=body.provider,
            connection_id=str(conn.id),
            redirect_uri=callback_url,
            scopes=provider_config.scopes if provider_config else None,
        )
    except Exception as e:
        await session.delete(conn)
        await session.commit()
        raise HTTPException(
            status_code=422,
            detail={"code": "oauth_begin_failed", "message": str(e)},
        ) from e

    conn.provider_config = {
        "redirect_url": body.redirect_url,
        "metadata": body.metadata or {},
        "oauth_state": result.state,
    }
    await session.commit()

    return {
        "data": CreateConnectionResponse(
            connection_id=str(conn.id),
            status=ConnectionStatus.PENDING,
            authorization_url=result.authorization_url,
        ),
        "meta": {"request_id": request_id},
    }


@router.get("")
async def list_connections(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: AsyncSession = Depends(get_session),
    request_id: str = Depends(get_request_id),
    status: str | None = Query(None),
    provider: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    from sqlalchemy import func

    query = select(Connection)
    if status:
        query = query.where(Connection.status == status)
    if provider:
        query = query.where(Connection.provider_key == provider)

    total_result = await session.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar_one()

    result = await session.execute(query.offset(offset).limit(limit))
    connections = result.scalars().all()

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
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: AsyncSession = Depends(get_session),
    request_id: str = Depends(get_request_id),
):
    conn = await get_connection(connection_id, session)
    return {
        "data": ConnectionResponse.from_model(conn),
        "meta": {"request_id": request_id},
    }


@router.delete("/{connection_id}", status_code=204)
async def delete_connection(
    connection_id: str,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: AsyncSession = Depends(get_session),
):
    conn = await get_connection(connection_id, session)
    await transition_to_revoked(conn.id, session, reason="Deleted by API")


@router.post("/{connection_id}/reauthorize", status_code=200)
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
    conn = await get_connection(connection_id, session)
    _validate_redirect_url_or_422(body.redirect_url, request, settings)

    if conn.status == ConnectionStatus.REVOKED:
        raise HTTPException(
            status_code=410,
            detail={
                "code": "connection_revoked",
                "message": "Cannot reauthorize a revoked connection",
            },
        )

    provider_config = await _get_provider_config(conn.provider_key, session)
    omni = _build_omni(session, encryption, settings, provider_config)
    callback_url = f"{settings.omnidapter_base_url}/oauth/{conn.provider_key}/callback"

    # Scope union: request at least the previously granted scopes to prevent downgrade
    existing_scopes = set(conn.granted_scopes or [])
    config_scopes = set(provider_config.scopes or []) if provider_config else set()
    union_scopes = list(existing_scopes | config_scopes) or None

    result = await omni.oauth.begin(
        provider=conn.provider_key,
        connection_id=str(conn.id),
        redirect_uri=callback_url,
        scopes=union_scopes,
    )

    from sqlalchemy import update

    await session.execute(
        update(Connection)
        .where(Connection.id == conn.id)
        .values(
            status=ConnectionStatus.PENDING,
            status_reason=None,
            provider_config={
                **(conn.provider_config or {}),
                "redirect_url": body.redirect_url,
                "oauth_state": result.state,
            },
        )
    )
    await session.commit()

    return {
        "data": {
            "connection_id": connection_id,
            "status": ConnectionStatus.PENDING,
            "authorization_url": result.authorization_url,
        },
        "meta": {"request_id": request_id},
    }
