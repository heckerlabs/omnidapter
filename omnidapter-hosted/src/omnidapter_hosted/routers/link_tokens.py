"""Link token management — create tokens for the Connect UI."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from omnidapter_server.database import get_session
from omnidapter_server.models.connection import Connection
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_hosted.config import HostedSettings, get_hosted_settings
from omnidapter_hosted.dependencies import (
    HostedAuthContext,
    get_hosted_auth_context,
    get_request_id,
)
from omnidapter_hosted.models.connection_owner import HostedConnectionOwner
from omnidapter_hosted.services.link_tokens import create_link_token

router = APIRouter(prefix="/link-tokens", tags=["link-tokens"])


class CreateLinkTokenRequest(BaseModel):
    end_user_id: str | None = None
    allowed_providers: list[str] | None = None
    redirect_uri: str | None = None
    # min 60s, max 24h; defaults to settings.omnidapter_link_token_ttl_seconds if omitted
    ttl_seconds: int | None = Field(default=None, gt=0, le=86400)
    # Reconnect: lock this token to an existing connection
    connection_id: uuid.UUID | None = None


async def _resolve_reconnect_provider(
    connection_id: uuid.UUID,
    tenant_id: uuid.UUID,
    session: AsyncSession,
) -> str:
    """Validate the connection belongs to tenant and return its provider key."""
    owner_result = await session.execute(
        select(HostedConnectionOwner).where(
            HostedConnectionOwner.connection_id == connection_id,
            HostedConnectionOwner.tenant_id == tenant_id,
        )
    )
    owner = owner_result.scalar_one_or_none()
    if owner is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "connection_not_found", "message": "Connection not found"},
        )

    conn_result = await session.execute(select(Connection).where(Connection.id == connection_id))
    conn = conn_result.scalar_one_or_none()
    if conn is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "connection_not_found", "message": "Connection not found"},
        )

    return conn.provider_key


@router.post("", status_code=201)
async def create_link_token_endpoint(
    body: CreateLinkTokenRequest,
    auth: Annotated[HostedAuthContext, Depends(get_hosted_auth_context)],
    session: AsyncSession = Depends(get_session),
    settings: HostedSettings = Depends(get_hosted_settings),
    request_id: str = Depends(get_request_id),
):
    """Create a short-lived link token for the Connect UI.

    Pass the returned token to the embedded or redirect Connect UI as a
    Bearer token. The token grants permission to list providers and initiate
    a connection on behalf of the tenant, scoped to ``end_user_id`` if provided.

    Set ``connection_id`` to create a *reconnect* token — the connect UI will
    skip provider selection and go directly to the authorization flow for the
    existing connection.
    """
    locked_provider_key: str | None = None
    if body.connection_id is not None:
        locked_provider_key = await _resolve_reconnect_provider(
            connection_id=body.connection_id,
            tenant_id=auth.tenant_id,
            session=session,
        )

    ttl = (
        body.ttl_seconds
        if body.ttl_seconds is not None
        else settings.omnidapter_link_token_ttl_seconds
    )
    raw_token, link_token = await create_link_token(
        tenant_id=auth.tenant_id,
        end_user_id=body.end_user_id,
        allowed_providers=body.allowed_providers,
        redirect_uri=body.redirect_uri,
        ttl_seconds=ttl,
        session=session,
        connection_id=body.connection_id,
        locked_provider_key=locked_provider_key,
    )

    return {
        "data": {
            "token": raw_token,
            "expires_at": link_token.expires_at.isoformat(),
            "connect_url": f"{settings.omnidapter_base_url}?token={raw_token}",
        },
        "meta": {"request_id": request_id},
    }
