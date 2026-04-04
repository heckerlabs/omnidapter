"""Tenant-scoped resource helpers for hosted app."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import HTTPException
from omnidapter_server.models.connection import Connection, ConnectionStatus
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_hosted.models.connection_owner import HostedConnectionOwner
from omnidapter_hosted.models.provider_config import HostedProviderConfig


@dataclass(frozen=True)
class TenantConnection:
    owner: HostedConnectionOwner
    connection: Connection


async def get_tenant_connection(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    connection_id: uuid.UUID,
) -> TenantConnection | None:
    owner_result = await session.execute(
        select(HostedConnectionOwner).where(
            HostedConnectionOwner.connection_id == connection_id,
            HostedConnectionOwner.tenant_id == tenant_id,
        )
    )
    owner = owner_result.scalar_one_or_none()
    if owner is None:
        return None

    conn_result = await session.execute(select(Connection).where(Connection.id == connection_id))
    connection = conn_result.scalar_one_or_none()
    if connection is None:
        return None

    return TenantConnection(owner=owner, connection=connection)


async def list_tenant_connections(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
) -> list[Connection]:
    result = await session.execute(
        select(Connection)
        .join(HostedConnectionOwner, HostedConnectionOwner.connection_id == Connection.id)
        .where(HostedConnectionOwner.tenant_id == tenant_id)
    )
    return list(result.scalars().all())


async def enforce_fallback_connection_limit(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    provider_key: str,
    limit: int,
) -> None:
    """Raise 422 if the tenant has no provider config and has reached the fallback connection limit."""
    provider_config = await get_tenant_provider_config(
        session=session, tenant_id=tenant_id, provider_key=provider_key
    )
    if provider_config is not None:
        return

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
    count = result.scalar_one()
    if count >= limit:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "fallback_connection_limit",
                "message": (
                    f"Fallback connection limit ({limit}) reached. "
                    "Configure your own OAuth app via /v1/provider-configs."
                ),
            },
        )


async def get_tenant_provider_config(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    provider_key: str,
) -> HostedProviderConfig | None:
    result = await session.execute(
        select(HostedProviderConfig).where(
            HostedProviderConfig.tenant_id == tenant_id,
            HostedProviderConfig.provider_key == provider_key,
        )
    )
    return result.scalar_one_or_none()
