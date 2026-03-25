"""Tenant-scoped provider config endpoints with server-compatible contracts."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from omnidapter_server.database import get_session
from omnidapter_server.dependencies import get_encryption_service
from omnidapter_server.encryption import EncryptionService
from omnidapter_server.schemas.provider_config import UpsertProviderConfigRequest
from omnidapter_server.services.provider_config_flows import (
    delete_provider_config_flow,
    get_provider_config_flow,
    list_provider_configs_flow,
    upsert_provider_config_flow,
)
from pydantic import BaseModel
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_hosted.dependencies import (
    HostedAuthContext,
    get_hosted_auth_context,
    get_request_id,
)
from omnidapter_hosted.models.provider_config import HostedProviderConfig

router = APIRouter(prefix="/provider-configs", tags=["provider-configs"])


class PatchProviderConfigRequest(BaseModel):
    is_enabled: bool


async def _list_configs(session: AsyncSession, tenant_id: uuid.UUID) -> list[HostedProviderConfig]:
    result = await session.execute(
        select(HostedProviderConfig).where(HostedProviderConfig.tenant_id == tenant_id)
    )
    return list(result.scalars().all())


async def _load_config(
    provider_key: str,
    session: AsyncSession,
    tenant_id: uuid.UUID,
) -> HostedProviderConfig | None:
    result = await session.execute(
        select(HostedProviderConfig).where(
            HostedProviderConfig.tenant_id == tenant_id,
            HostedProviderConfig.provider_key == provider_key,
        )
    )
    return result.scalar_one_or_none()


def _create_config(
    provider_key: str,
    client_id_enc: str,
    client_secret_enc: str,
    scopes: list[str] | None,
    tenant_id: uuid.UUID,
) -> HostedProviderConfig:
    return HostedProviderConfig(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        provider_key=provider_key,
        auth_kind="oauth2",
        client_id_encrypted=client_id_enc,
        client_secret_encrypted=client_secret_enc,
        scopes=scopes,
    )


async def _delete_config(provider_key: str, session: AsyncSession, tenant_id: uuid.UUID) -> None:
    await session.execute(
        delete(HostedProviderConfig).where(
            HostedProviderConfig.tenant_id == tenant_id,
            HostedProviderConfig.provider_key == provider_key,
        )
    )


@router.get("")
async def list_provider_configs(
    auth: Annotated[HostedAuthContext, Depends(get_hosted_auth_context)],
    session: AsyncSession = Depends(get_session),
    request_id: str = Depends(get_request_id),
):
    return {
        "data": await list_provider_configs_flow(
            session=session,
            list_configs=lambda s: _list_configs(s, auth.tenant_id),
        ),
        "meta": {"request_id": request_id},
    }


@router.get("/{provider_key}")
async def get_provider_config(
    provider_key: str,
    auth: Annotated[HostedAuthContext, Depends(get_hosted_auth_context)],
    session: AsyncSession = Depends(get_session),
    request_id: str = Depends(get_request_id),
):
    return {
        "data": await get_provider_config_flow(
            provider_key=provider_key,
            session=session,
            load_config=lambda p, s: _load_config(p, s, auth.tenant_id),
        ),
        "meta": {"request_id": request_id},
    }


@router.put("/{provider_key}")
async def upsert_provider_config(
    provider_key: str,
    body: UpsertProviderConfigRequest,
    auth: Annotated[HostedAuthContext, Depends(get_hosted_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    request_id: str = Depends(get_request_id),
):
    return {
        "data": await upsert_provider_config_flow(
            provider_key=provider_key,
            body=body,
            encryption=encryption,
            session=session,
            load_config=lambda p, s: _load_config(p, s, auth.tenant_id),
            create_config=lambda p, c_id, c_secret, scopes: _create_config(
                p,
                c_id,
                c_secret,
                scopes,
                auth.tenant_id,
            ),
        ),
        "meta": {"request_id": request_id},
    }


@router.patch("/{provider_key}")
async def patch_provider_config(
    provider_key: str,
    body: PatchProviderConfigRequest,
    auth: Annotated[HostedAuthContext, Depends(get_hosted_auth_context)],
    session: AsyncSession = Depends(get_session),
    request_id: str = Depends(get_request_id),
):
    """Enable or disable a provider for the Connect UI.

    If no config exists yet, one is created with ``is_enabled`` set and null
    OAuth credentials — this lets an org explicitly disable a fallback provider
    or pre-stage an enabled record for a non-OAuth provider.
    """
    existing = await _load_config(provider_key, session, auth.tenant_id)

    if existing is None:
        # Create a stub config record so we can record the is_enabled preference
        new_cfg = HostedProviderConfig(
            id=uuid.uuid4(),
            tenant_id=auth.tenant_id,
            provider_key=provider_key,
            auth_kind="oauth2",
            is_enabled=body.is_enabled,
        )
        session.add(new_cfg)
        await session.commit()
        await session.refresh(new_cfg)
        return {
            "data": {"provider_key": provider_key, "is_enabled": new_cfg.is_enabled},
            "meta": {"request_id": request_id},
        }

    await session.execute(
        update(HostedProviderConfig)
        .where(
            HostedProviderConfig.tenant_id == auth.tenant_id,
            HostedProviderConfig.provider_key == provider_key,
        )
        .values(is_enabled=body.is_enabled)
    )
    await session.commit()
    return {
        "data": {"provider_key": provider_key, "is_enabled": body.is_enabled},
        "meta": {"request_id": request_id},
    }


@router.delete("/{provider_key}", status_code=204)
async def delete_provider_config(
    provider_key: str,
    auth: Annotated[HostedAuthContext, Depends(get_hosted_auth_context)],
    session: AsyncSession = Depends(get_session),
):
    await delete_provider_config_flow(
        provider_key=provider_key,
        session=session,
        load_config=lambda p, s: _load_config(p, s, auth.tenant_id),
        delete_config=lambda p, s: _delete_config(p, s, auth.tenant_id),
    )
