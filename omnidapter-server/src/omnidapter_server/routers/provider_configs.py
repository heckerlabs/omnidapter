"""Provider config (OAuth credentials) endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_server.database import get_session
from omnidapter_server.dependencies import (
    AuthContext,
    get_auth_context,
    get_encryption_service,
    get_request_id,
)
from omnidapter_server.encryption import EncryptionService
from omnidapter_server.models.provider_config import ProviderConfig
from omnidapter_server.schemas.provider_config import UpsertProviderConfigRequest
from omnidapter_server.services.provider_config_flows import (
    delete_provider_config_flow,
    get_provider_config_flow,
    list_provider_configs_flow,
    upsert_provider_config_flow,
)

router = APIRouter(prefix="/provider-configs", tags=["provider-configs"])


async def _list_configs(session: AsyncSession) -> list[ProviderConfig]:
    result = await session.execute(select(ProviderConfig))
    return list(result.scalars().all())


async def _load_config(provider_key: str, session: AsyncSession) -> ProviderConfig | None:
    result = await session.execute(
        select(ProviderConfig).where(ProviderConfig.provider_key == provider_key)
    )
    return result.scalar_one_or_none()


def _create_config(
    provider_key: str,
    client_id_enc: str,
    client_secret_enc: str,
    scopes: list[str] | None,
) -> ProviderConfig:
    return ProviderConfig(
        id=uuid.uuid4(),
        provider_key=provider_key,
        auth_kind="oauth2",
        client_id_encrypted=client_id_enc,
        client_secret_encrypted=client_secret_enc,
        scopes=scopes,
        is_fallback=False,
    )


async def _delete_config(provider_key: str, session: AsyncSession) -> None:
    await session.execute(delete(ProviderConfig).where(ProviderConfig.provider_key == provider_key))


@router.get("")
async def list_provider_configs(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: AsyncSession = Depends(get_session),
    request_id: str = Depends(get_request_id),
):
    return {
        "data": await list_provider_configs_flow(session=session, list_configs=_list_configs),
        "meta": {"request_id": request_id},
    }


@router.get("/{provider_key}")
async def get_provider_config(
    provider_key: str,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: AsyncSession = Depends(get_session),
    request_id: str = Depends(get_request_id),
):
    return {
        "data": await get_provider_config_flow(
            provider_key=provider_key,
            session=session,
            load_config=_load_config,
        ),
        "meta": {"request_id": request_id},
    }


@router.put("/{provider_key}")
async def upsert_provider_config(
    provider_key: str,
    body: UpsertProviderConfigRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
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
            load_config=_load_config,
            create_config=_create_config,
        ),
        "meta": {"request_id": request_id},
    }


@router.delete("/{provider_key}", status_code=204)
async def delete_provider_config(
    provider_key: str,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: AsyncSession = Depends(get_session),
):
    await delete_provider_config_flow(
        provider_key=provider_key,
        session=session,
        load_config=_load_config,
        delete_config=_delete_config,
    )
