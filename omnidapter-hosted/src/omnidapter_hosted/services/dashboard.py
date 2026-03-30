"""Dashboard service — profile, tenant, member, API key, connection, and provider config flows."""

from __future__ import annotations

import uuid
from typing import cast

from fastapi import HTTPException
from omnidapter_server.encryption import EncryptionService
from omnidapter_server.models.connection import Connection, ConnectionStatus
from omnidapter_server.services.connection_health import transition_to_revoked
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_hosted.models.api_key import HostedAPIKey
from omnidapter_hosted.models.connection_owner import HostedConnectionOwner
from omnidapter_hosted.models.membership import HostedMembership, MemberRole
from omnidapter_hosted.models.provider_config import HostedProviderConfig
from omnidapter_hosted.models.tenant import Tenant
from omnidapter_hosted.models.user import HostedUser
from omnidapter_hosted.services.auth import generate_hosted_api_key


def _require_admin(role: str) -> None:
    if role not in (MemberRole.OWNER, MemberRole.ADMIN):
        raise HTTPException(
            status_code=403,
            detail={"code": "forbidden", "message": "Owner or admin role required"},
        )


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


async def update_user_name(user: HostedUser, name: str, session: AsyncSession) -> HostedUser:
    user.name = name
    await session.commit()
    await session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Tenant
# ---------------------------------------------------------------------------


async def update_tenant_name(tenant: Tenant, name: str, role: str, session: AsyncSession) -> Tenant:
    _require_admin(role)
    tenant.name = name
    await session.commit()
    await session.refresh(tenant)
    return tenant


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------


async def list_members(
    tenant_id: uuid.UUID,
    session: AsyncSession,
) -> list[tuple[HostedMembership, HostedUser]]:
    result = await session.execute(
        select(HostedMembership, HostedUser)
        .join(HostedUser, HostedUser.id == HostedMembership.user_id)
        .where(HostedMembership.tenant_id == tenant_id)
    )
    return cast(list[tuple[HostedMembership, HostedUser]], result.all())


async def remove_member(
    tenant_id: uuid.UUID,
    target_user_id: uuid.UUID,
    requesting_role: str,
    requesting_user_id: uuid.UUID,
    session: AsyncSession,
) -> None:
    _require_admin(requesting_role)

    result = await session.execute(
        select(HostedMembership)
        .where(HostedMembership.tenant_id == tenant_id)
        .where(HostedMembership.user_id == target_user_id)
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "Member not found"}
        )
    if membership.role == MemberRole.OWNER:
        raise HTTPException(
            status_code=400,
            detail={"code": "cannot_remove_owner", "message": "Cannot remove the tenant owner"},
        )
    if target_user_id == requesting_user_id:
        raise HTTPException(
            status_code=400,
            detail={"code": "cannot_remove_self", "message": "Cannot remove yourself"},
        )

    await session.delete(membership)
    await session.commit()


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------


async def list_api_keys_flow(tenant_id: uuid.UUID, session: AsyncSession) -> list[HostedAPIKey]:
    result = await session.execute(select(HostedAPIKey).where(HostedAPIKey.tenant_id == tenant_id))
    return list(result.scalars().all())


async def create_api_key_flow(
    tenant_id: uuid.UUID, name: str, role: str, session: AsyncSession
) -> tuple[str, HostedAPIKey]:
    """Create a new API key. Returns ``(raw_key, model)``; raw_key is shown once."""
    _require_admin(role)
    raw_key, key_hash, key_prefix = generate_hosted_api_key()
    api_key = HostedAPIKey(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name=name,
        key_hash=key_hash,
        key_prefix=key_prefix,
    )
    session.add(api_key)
    await session.commit()
    await session.refresh(api_key)
    return raw_key, api_key


async def revoke_api_key_flow(
    key_id: uuid.UUID, tenant_id: uuid.UUID, role: str, session: AsyncSession
) -> None:
    _require_admin(role)
    result = await session.execute(
        select(HostedAPIKey).where(
            HostedAPIKey.id == key_id,
            HostedAPIKey.tenant_id == tenant_id,
        )
    )
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "API key not found"}
        )
    await session.delete(api_key)
    await session.commit()


# ---------------------------------------------------------------------------
# Connections (dashboard read-only view + force-revoke)
# ---------------------------------------------------------------------------


async def list_connections_flow(tenant_id: uuid.UUID, session: AsyncSession) -> list[Connection]:
    result = await session.execute(
        select(Connection)
        .join(HostedConnectionOwner, HostedConnectionOwner.connection_id == Connection.id)
        .where(HostedConnectionOwner.tenant_id == tenant_id)
        .where(Connection.status != ConnectionStatus.REVOKED)
        .order_by(Connection.created_at.desc())
    )
    return list(result.scalars().all())


async def revoke_connection_flow(
    connection_id: uuid.UUID, tenant_id: uuid.UUID, role: str, session: AsyncSession
) -> None:
    _require_admin(role)
    result = await session.execute(
        select(Connection)
        .join(HostedConnectionOwner, HostedConnectionOwner.connection_id == Connection.id)
        .where(Connection.id == connection_id, HostedConnectionOwner.tenant_id == tenant_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "Connection not found"}
        )
    await transition_to_revoked(connection_id, session, reason="Revoked from dashboard")


# ---------------------------------------------------------------------------
# Provider configs
# ---------------------------------------------------------------------------


async def list_provider_configs_flow(
    tenant_id: uuid.UUID, session: AsyncSession
) -> list[HostedProviderConfig]:
    result = await session.execute(
        select(HostedProviderConfig).where(HostedProviderConfig.tenant_id == tenant_id)
    )
    return list(result.scalars().all())


async def upsert_provider_config_flow(
    tenant_id: uuid.UUID,
    provider_key: str,
    client_id: str,
    client_secret: str,
    scopes: list[str] | None,
    role: str,
    encryption: EncryptionService,
    session: AsyncSession,
) -> HostedProviderConfig:
    _require_admin(role)
    result = await session.execute(
        select(HostedProviderConfig).where(
            HostedProviderConfig.tenant_id == tenant_id,
            HostedProviderConfig.provider_key == provider_key,
        )
    )
    config = result.scalar_one_or_none()

    encrypted_id = encryption.encrypt(client_id)
    encrypted_secret = encryption.encrypt(client_secret)

    if config is None:
        config = HostedProviderConfig(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            provider_key=provider_key,
            auth_kind="oauth2",
            client_id_encrypted=encrypted_id,
            client_secret_encrypted=encrypted_secret,
            scopes=scopes,
        )
        session.add(config)
    else:
        config.client_id_encrypted = encrypted_id
        config.client_secret_encrypted = encrypted_secret
        config.scopes = scopes

    await session.commit()
    await session.refresh(config)
    return config


async def delete_provider_config_flow(
    tenant_id: uuid.UUID, provider_key: str, role: str, session: AsyncSession
) -> None:
    _require_admin(role)
    result = await session.execute(
        select(HostedProviderConfig).where(
            HostedProviderConfig.tenant_id == tenant_id,
            HostedProviderConfig.provider_key == provider_key,
        )
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "Provider config not found"},
        )
    await session.delete(config)
    await session.commit()
