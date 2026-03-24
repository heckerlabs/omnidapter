"""Link token management — create tokens for the Connect UI."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from omnidapter_server.database import get_session
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_hosted.config import HostedSettings, get_hosted_settings
from omnidapter_hosted.dependencies import (
    HostedAuthContext,
    get_hosted_auth_context,
    get_request_id,
)
from omnidapter_hosted.services.link_tokens import create_link_token

router = APIRouter(prefix="/link-tokens", tags=["link-tokens"])


class CreateLinkTokenRequest(BaseModel):
    end_user_id: str | None = None
    allowed_providers: list[str] | None = None
    redirect_uri: str | None = None
    # min 60s, max 24h; defaults to settings.link_token_ttl_seconds if omitted
    ttl_seconds: int | None = Field(default=None, gt=0, le=86400)


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
    """
    ttl = body.ttl_seconds if body.ttl_seconds is not None else settings.link_token_ttl_seconds
    raw_token, link_token = await create_link_token(
        tenant_id=auth.tenant_id,
        end_user_id=body.end_user_id,
        allowed_providers=body.allowed_providers,
        redirect_uri=body.redirect_uri,
        ttl_seconds=ttl,
        session=session,
    )

    return {
        "data": {
            "token": raw_token,
            "expires_at": link_token.expires_at.isoformat(),
        },
        "meta": {"request_id": request_id},
    }
