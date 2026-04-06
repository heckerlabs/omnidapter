"""Link token generation and verification — hosted wrapper around server service."""

from __future__ import annotations

import uuid

from omnidapter_server.models.link_token import LinkToken
from omnidapter_server.services.link_tokens import (
    create_link_token as _server_create_link_token,
)
from omnidapter_server.services.link_tokens import (
    generate_link_token as generate_link_token,  # re-export
)
from omnidapter_server.services.link_tokens import (
    verify_link_token as verify_link_token,  # re-export
)
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_hosted.models.link_token_owner import HostedLinkTokenOwner


async def create_link_token(
    tenant_id: uuid.UUID,
    end_user_id: str | None,
    allowed_providers: list[str] | None,
    redirect_uri: str | None,
    ttl_seconds: int,
    session: AsyncSession,
    *,
    connection_id: uuid.UUID | None = None,
    locked_provider_key: str | None = None,
) -> tuple[str, LinkToken]:
    """Create and persist a hosted link token. Returns (raw_token, model).

    Wraps the server's ``create_link_token`` and adds a companion
    ``HostedLinkTokenOwner`` row to associate the token with a tenant.
    """

    async def _persist_owner(lt: LinkToken, s: AsyncSession) -> None:
        s.add(
            HostedLinkTokenOwner(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                link_token_id=lt.id,
            )
        )

    return await _server_create_link_token(
        end_user_id=end_user_id,
        allowed_providers=allowed_providers,
        redirect_uri=redirect_uri,
        ttl_seconds=ttl_seconds,
        session=session,
        connection_id=connection_id,
        locked_provider_key=locked_provider_key,
        persist_post_create=_persist_owner,
    )
