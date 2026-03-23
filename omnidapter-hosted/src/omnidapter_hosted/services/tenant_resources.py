"""Tenant-scoped resource helpers for hosted app."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from omnidapter_server.models.connection import Connection
from sqlalchemy import select
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
