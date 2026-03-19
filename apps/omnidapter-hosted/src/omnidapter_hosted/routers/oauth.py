"""Hosted OAuth callback endpoints with tenant-scoped provider config resolution."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from omnidapter import Omnidapter
from omnidapter_server.config import Settings, get_settings
from omnidapter_server.database import get_session
from omnidapter_server.encryption import EncryptionService
from omnidapter_server.models.connection import Connection
from omnidapter_server.models.oauth_state import OAuthState
from omnidapter_server.services.oauth_flows import (
    OAuthCallbackParams,
    append_query_params,
    oauth_callback_flow,
)
from omnidapter_server.stores.credential_store import DatabaseCredentialStore
from omnidapter_server.stores.factory import build_oauth_state_store
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_hosted.dependencies import get_encryption_service
from omnidapter_hosted.models.connection_owner import HostedConnectionOwner
from omnidapter_hosted.services.provider_registry import build_hosted_provider_registry

router = APIRouter(prefix="/oauth", tags=["oauth"])


async def _load_oauth_state(state_token: str, session: AsyncSession) -> OAuthState | None:
    result = await session.execute(select(OAuthState).where(OAuthState.state_token == state_token))
    return result.scalar_one_or_none()


async def _load_connection_for_state(
    state_row: OAuthState, session: AsyncSession
) -> Connection | None:
    conn_result = await session.execute(
        select(Connection).where(Connection.id == state_row.connection_id)
    )
    conn = conn_result.scalar_one_or_none()
    if conn is None:
        return None

    owner_result = await session.execute(
        select(HostedConnectionOwner).where(
            HostedConnectionOwner.connection_id == state_row.connection_id
        )
    )
    owner = owner_result.scalar_one_or_none()
    if owner is None:
        return None
    return conn


async def _load_owner_tenant_id(
    connection_id,
    session: AsyncSession,
):
    owner_result = await session.execute(
        select(HostedConnectionOwner).where(HostedConnectionOwner.connection_id == connection_id)
    )
    owner = owner_result.scalar_one_or_none()
    if owner is None:
        return None
    return owner.tenant_id


async def _load_connection_with_owner(
    *,
    session: AsyncSession,
    connection_id,
) -> tuple[Connection | None, HostedConnectionOwner | None]:
    conn_result = await session.execute(select(Connection).where(Connection.id == connection_id))
    conn = conn_result.scalar_one_or_none()
    if conn is None:
        return None, None

    owner_result = await session.execute(
        select(HostedConnectionOwner).where(HostedConnectionOwner.connection_id == connection_id)
    )
    owner = owner_result.scalar_one_or_none()
    return conn, owner


async def _build_omni(
    provider_key: str,
    connection: Connection,
    session: AsyncSession,
    encryption: EncryptionService,
    settings: Settings,
) -> Omnidapter:
    tenant_id = await _load_owner_tenant_id(connection.id, session)
    if tenant_id is None:
        raise ValueError("Connection owner not found")

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


def _append_query_params(url: str, **params: str) -> str:
    return append_query_params(url, **params)


@router.get("/{provider_key}/callback")
async def oauth_callback(
    provider_key: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    encryption: EncryptionService = Depends(get_encryption_service),
    settings: Settings = Depends(get_settings),
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
    error_description: str | None = Query(None),
):
    """Handle OAuth callback from provider."""
    return await oauth_callback_flow(
        params=OAuthCallbackParams(
            provider_key=provider_key,
            code=code,
            state=state,
            error=error,
            error_description=error_description,
        ),
        request=request,
        session=session,
        settings=settings,
        load_oauth_state=_load_oauth_state,
        load_connection_for_state=_load_connection_for_state,
        build_omni=lambda flow_provider_key, conn, flow_session: _build_omni(
            flow_provider_key,
            conn,
            flow_session,
            encryption,
            settings,
        ),
    )
