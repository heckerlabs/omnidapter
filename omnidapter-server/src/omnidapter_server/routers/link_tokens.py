"""Link token management — create tokens for the Connect UI."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_server.config import Settings, get_settings
from omnidapter_server.database import get_session
from omnidapter_server.dependencies import AuthContext, get_auth_context, get_request_id
from omnidapter_server.models.connection import Connection
from omnidapter_server.services.link_tokens import create_link_token

router = APIRouter(prefix="/link-tokens", tags=["link-tokens"])


class CreateLinkTokenRequest(BaseModel):
    end_user_id: str | None = None
    allowed_providers: list[str] | None = None
    redirect_uri: str | None = None
    # min 60s, max 24h; defaults to settings.omnidapter_link_token_ttl_seconds if omitted
    ttl_seconds: int | None = Field(default=None, ge=60, le=86400)
    # Reconnect: lock this token to an existing connection
    connection_id: uuid.UUID | None = None


async def _resolve_reconnect_provider(
    connection_id: uuid.UUID,
    session: AsyncSession,
) -> str:
    """Validate the connection exists and return its provider key."""
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
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
):
    """Create a short-lived link token for the Connect UI.

    Pass the returned token to the embedded or redirect Connect UI as a
    Bearer token. The token grants permission to list providers and initiate
    a connection, optionally scoped to ``end_user_id``.

    Set ``connection_id`` to create a *reconnect* token — the connect UI will
    skip provider selection and go directly to the authorization flow for the
    existing connection.
    """
    locked_provider_key: str | None = None
    if body.connection_id is not None:
        locked_provider_key = await _resolve_reconnect_provider(
            connection_id=body.connection_id,
            session=session,
        )

    ttl = (
        body.ttl_seconds
        if body.ttl_seconds is not None
        else settings.omnidapter_link_token_ttl_seconds
    )
    raw_token, link_token = await create_link_token(
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
        },
        "meta": {"request_id": request_id},
    }
