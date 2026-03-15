"""Connection management endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from omnidapter import Omnidapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_api.config import Settings, get_settings
from omnidapter_api.database import get_session
from omnidapter_api.dependencies import (
    AuthContext,
    get_auth_context,
    get_encryption_service,
    get_request_id,
)
from omnidapter_api.encryption import EncryptionService
from omnidapter_api.models.connection import Connection, ConnectionStatus
from omnidapter_api.models.provider_config import ProviderConfig
from omnidapter_api.pagination import build_pagination_meta
from omnidapter_api.schemas.connection import (
    ConnectionResponse,
    CreateConnectionRequest,
    CreateConnectionResponse,
    ReauthorizeConnectionRequest,
)
from omnidapter_api.services.connection_health import transition_to_revoked
from omnidapter_api.services.provider_overrides import (
    register_fallback_provider_credentials,
    register_provider_credentials,
)
from omnidapter_api.stores.credential_store import DatabaseCredentialStore
from omnidapter_api.stores.oauth_state_store import DatabaseOAuthStateStore

router = APIRouter(prefix="/connections", tags=["connections"])


def _build_omni(
    session: AsyncSession,
    encryption: EncryptionService,
    settings: Settings,
    provider_config: ProviderConfig | None = None,
) -> Omnidapter:
    """Build an Omnidapter instance with DB-backed stores and optional custom provider config."""
    cred_store = DatabaseCredentialStore(session=session, encryption=encryption)
    state_store = DatabaseOAuthStateStore(session=session, encryption=encryption)

    omni = Omnidapter(
        credential_store=cred_store,
        oauth_state_store=state_store,
        auto_register_by_env=True,
    )
    register_fallback_provider_credentials(omni, settings)

    # If the org has their own provider config, override the provider instance.
    if provider_config and not provider_config.is_fallback:
        client_id = encryption.decrypt(provider_config.client_id_encrypted or "")
        client_secret = encryption.decrypt(provider_config.client_secret_encrypted or "")
        register_provider_credentials(omni, provider_config.provider_key, client_id, client_secret)

    return omni


async def _get_provider_config(
    org_id: uuid.UUID,
    provider_key: str,
    session: AsyncSession,
) -> ProviderConfig | None:
    result = await session.execute(
        select(ProviderConfig).where(
            ProviderConfig.organization_id == org_id,
            ProviderConfig.provider_key == provider_key,
        )
    )
    return result.scalar_one_or_none()


async def _get_connection(
    connection_id: str,
    org_id: uuid.UUID,
    session: AsyncSession,
) -> Connection:
    try:
        conn_uuid = uuid.UUID(connection_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "connection_not_found", "message": "Connection not found"},
        ) from exc

    result = await session.execute(
        select(Connection).where(
            Connection.id == conn_uuid,
            Connection.organization_id == org_id,
        )
    )
    conn = result.scalar_one_or_none()
    if conn is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "connection_not_found", "message": "Connection not found"},
        )
    return conn


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
    provider_config = await _get_provider_config(auth.org_id, body.provider, session)

    # Check fallback connection limit
    if provider_config is None or provider_config.is_fallback:
        existing_result = await session.execute(
            select(Connection).where(
                Connection.organization_id == auth.org_id,
                Connection.provider_key == body.provider,
                Connection.status != ConnectionStatus.REVOKED,
            )
        )
        existing = existing_result.scalars().all()
        if len(existing) >= settings.omnidapter_fallback_connection_limit:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "fallback_connection_limit",
                    "message": f"Fallback connection limit ({settings.omnidapter_fallback_connection_limit}) reached. Configure your own OAuth app.",
                },
            )

    # Create connection record in pending state
    conn = Connection(
        id=uuid.uuid4(),
        organization_id=auth.org_id,
        provider_key=body.provider,
        external_id=body.external_id,
        status=ConnectionStatus.PENDING,
        provider_config=None,
    )
    session.add(conn)
    await session.commit()
    await session.refresh(conn)

    try:
        omni = _build_omni(session, encryption, settings, provider_config)
        callback_url = f"{settings.omnidapter_base_url}/oauth/{body.provider}/callback"
        oauth_begin = await omni.oauth.begin(
            provider=body.provider,
            connection_id=str(conn.id),
            redirect_uri=callback_url,
            scopes=provider_config.scopes if provider_config else None,
        )
    except Exception as e:
        # Clean up the connection if OAuth begin fails
        await session.delete(conn)
        await session.commit()
        raise HTTPException(
            status_code=422,
            detail={"code": "oauth_begin_failed", "message": str(e)},
        ) from e

    # Store the redirect_url in connection's provider_config JSONB
    conn.provider_config = {
        "redirect_url": body.redirect_url,
        "metadata": body.metadata or {},
        "oauth_state": oauth_begin.state,
    }
    await session.commit()

    return {
        "data": CreateConnectionResponse(
            connection_id=str(conn.id),
            status=ConnectionStatus.PENDING,
            authorization_url=oauth_begin.authorization_url,
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
    query = select(Connection).where(Connection.organization_id == auth.org_id)
    if status:
        query = query.where(Connection.status == status)
    if provider:
        query = query.where(Connection.provider_key == provider)

    count_query = select(Connection).where(Connection.organization_id == auth.org_id)
    if status:
        count_query = count_query.where(Connection.status == status)
    if provider:
        count_query = count_query.where(Connection.provider_key == provider)

    from sqlalchemy import func

    total_result = await session.execute(select(func.count()).select_from(count_query.subquery()))
    total = total_result.scalar_one()

    result = await session.execute(query.offset(offset).limit(limit))
    connections = result.scalars().all()

    return {
        "data": [ConnectionResponse.from_model(c) for c in connections],
        "meta": {
            "request_id": request_id,
            "pagination": build_pagination_meta(total=total, limit=limit, offset=offset),
        },
    }


@router.get("/{connection_id}")
async def get_connection(
    connection_id: str,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: AsyncSession = Depends(get_session),
    request_id: str = Depends(get_request_id),
):
    conn = await _get_connection(connection_id, auth.org_id, session)
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
    conn = await _get_connection(connection_id, auth.org_id, session)
    await transition_to_revoked(conn.id, session, reason="Deleted by organization")


@router.post("/{connection_id}/reauthorize", status_code=200)
async def reauthorize_connection(
    connection_id: str,
    body: ReauthorizeConnectionRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
):
    conn = await _get_connection(connection_id, auth.org_id, session)

    if conn.status == ConnectionStatus.REVOKED:
        raise HTTPException(
            status_code=410,
            detail={
                "code": "connection_revoked",
                "message": "Cannot reauthorize a revoked connection",
            },
        )

    provider_config = await _get_provider_config(auth.org_id, conn.provider_key, session)

    try:
        omni = _build_omni(session, encryption, settings, provider_config)
        callback_url = f"{settings.omnidapter_base_url}/oauth/{conn.provider_key}/callback"
        result = await omni.oauth.begin(
            provider=conn.provider_key,
            connection_id=str(conn.id),
            redirect_uri=callback_url,
            scopes=provider_config.scopes if provider_config else None,
        )
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail={"code": "oauth_begin_failed", "message": str(e)},
        ) from e

    # Update connection back to pending
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
