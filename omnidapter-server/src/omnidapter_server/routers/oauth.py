"""OAuth callback endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from omnidapter import Omnidapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_server.config import Settings, get_settings
from omnidapter_server.database import get_session
from omnidapter_server.dependencies import get_encryption_service
from omnidapter_server.encryption import EncryptionService
from omnidapter_server.models.connection import Connection
from omnidapter_server.provider_registry import build_provider_registry
from omnidapter_server.services.oauth_flows import (
    OAuthCallbackParams,
    append_query_params,
    oauth_callback_flow,
)
from omnidapter_server.stores.credential_store import DatabaseCredentialStore
from omnidapter_server.stores.factory import build_oauth_state_store

router = APIRouter(prefix="/oauth", tags=["oauth"])


async def _load_connection_by_id(connection_id: str, session: AsyncSession) -> Connection | None:
    try:
        conn_uuid = uuid.UUID(connection_id)
    except ValueError:
        return None

    conn_result = await session.execute(select(Connection).where(Connection.id == conn_uuid))
    return conn_result.scalar_one_or_none()


async def _build_omni(
    provider_key: str,
    connection: Connection,
    session: AsyncSession,
    encryption: EncryptionService,
    settings: Settings,
    oauth_state_store,
) -> Omnidapter:
    cred_store = DatabaseCredentialStore(session=session, encryption=encryption)
    registry = build_provider_registry(settings)

    return Omnidapter(
        credential_store=cred_store,
        oauth_state_store=oauth_state_store,
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
    state_store = build_oauth_state_store(settings, session, encryption)

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
        load_oauth_state=state_store.load_state,
        load_connection_by_id=_load_connection_by_id,
        build_omni=lambda flow_provider_key, conn, flow_session: _build_omni(
            flow_provider_key,
            conn,
            flow_session,
            encryption,
            settings,
            state_store,
        ),
    )
