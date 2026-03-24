"""Connect UI endpoints — authenticated via link token (lt_*).

These routes are the only surface available to end-users connecting their
calendars. They are intentionally narrow: list available providers and
initiate an OAuth connection.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from omnidapter import Omnidapter
from omnidapter_server.database import get_session
from omnidapter_server.encryption import EncryptionService
from omnidapter_server.models.connection import Connection
from omnidapter_server.schemas.connection import (
    CreateConnectionRequest,
    CreateConnectionResponse,
)
from omnidapter_server.services.connection_flows import create_connection_flow
from omnidapter_server.stores.credential_store import DatabaseCredentialStore
from omnidapter_server.stores.factory import build_oauth_state_store
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_hosted.config import HostedSettings, get_hosted_settings
from omnidapter_hosted.dependencies import (
    LinkTokenContext,
    get_encryption_service,
    get_link_token_context,
    get_request_id,
)
from omnidapter_hosted.models.connection_owner import HostedConnectionOwner
from omnidapter_hosted.services.provider_registry import build_hosted_provider_registry
from omnidapter_hosted.services.tenant_resources import get_tenant_provider_config

router = APIRouter(prefix="/connect", tags=["connect"])


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


async def _persist_owner(conn: Connection, session: AsyncSession, tenant_id: uuid.UUID) -> None:
    session.add(
        HostedConnectionOwner(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            connection_id=conn.id,
        )
    )


async def _count_active_connections(
    provider_key: str,
    session: AsyncSession,
    tenant_id: uuid.UUID,
) -> int:
    from omnidapter_server.models.connection import ConnectionStatus

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


@router.get("/providers")
async def list_providers(
    link_token: Annotated[LinkTokenContext, Depends(get_link_token_context)],
    settings: HostedSettings = Depends(get_hosted_settings),
    request_id: str = Depends(get_request_id),
):
    """List providers available for this link token.

    If ``allowed_providers`` was set when the token was created, only those
    providers are returned. Otherwise all configured providers are returned.
    """
    from omnidapter import Omnidapter
    from omnidapter_server.provider_registry import build_provider_registry
    from omnidapter_server.services.provider_metadata_flows import list_providers_flow

    omni = Omnidapter(registry=build_provider_registry(settings))
    providers = list_providers_flow(omni)

    if link_token.allowed_providers is not None:
        allowed = set(link_token.allowed_providers)
        providers = [p for p in providers if p["key"] in allowed]

    return {"data": providers, "meta": {"request_id": request_id}}


@router.post("/connections", status_code=201)
async def create_connection(
    body: CreateConnectionRequest,
    request: Request,
    link_token: Annotated[LinkTokenContext, Depends(get_link_token_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: HostedSettings = Depends(get_hosted_settings),
    request_id: str = Depends(get_request_id),
):
    """Initiate an OAuth connection on behalf of the link token's tenant.

    Returns the authorization URL to redirect the end-user to.
    """
    tenant_id = link_token.tenant_id

    # Optionally scope external_id to the end_user_id if not already set
    if not body.external_id and link_token.end_user_id:
        body = body.model_copy(update={"external_id": link_token.end_user_id})

    flow_result = await create_connection_flow(
        body=body,
        request=request,
        session=session,
        settings=settings,
        load_provider_config=lambda provider_key, s: get_tenant_provider_config(
            session=s,
            tenant_id=tenant_id,
            provider_key=provider_key,
        ),
        count_active_connections=lambda provider_key, s: _count_active_connections(
            provider_key, s, tenant_id
        ),
        build_omni=lambda s, provider_key, provider_config: _build_omni(
            s, encryption, settings, tenant_id, provider_key, provider_config
        ),
        persist_post_create=lambda conn, s: _persist_owner(conn, s, tenant_id),
    )

    return {
        "data": CreateConnectionResponse(
            connection_id=flow_result.connection_id,
            status=flow_result.status,
            authorization_url=flow_result.authorization_url,
        ),
        "meta": {"request_id": request_id},
    }
