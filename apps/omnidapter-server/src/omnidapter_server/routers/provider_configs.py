"""Provider config (OAuth credentials) endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
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
from omnidapter_server.schemas.provider_config import (
    ProviderConfigResponse,
    UpsertProviderConfigRequest,
)

router = APIRouter(prefix="/provider-configs", tags=["provider-configs"])


@router.get("")
async def list_provider_configs(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: AsyncSession = Depends(get_session),
    request_id: str = Depends(get_request_id),
):
    result = await session.execute(select(ProviderConfig))
    configs = result.scalars().all()
    return {
        "data": [ProviderConfigResponse.from_model(c) for c in configs],
        "meta": {"request_id": request_id},
    }


@router.get("/{provider_key}")
async def get_provider_config(
    provider_key: str,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: AsyncSession = Depends(get_session),
    request_id: str = Depends(get_request_id),
):
    result = await session.execute(
        select(ProviderConfig).where(ProviderConfig.provider_key == provider_key)
    )
    cfg = result.scalar_one_or_none()
    if cfg is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "provider_config_not_found", "message": "Provider config not found"},
        )
    return {
        "data": ProviderConfigResponse.from_model(cfg),
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
    if not encryption._current_key:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "encryption_not_configured",
                "message": "Encryption key is not configured",
            },
        )

    result = await session.execute(
        select(ProviderConfig).where(ProviderConfig.provider_key == provider_key)
    )
    cfg = result.scalar_one_or_none()

    client_id_enc = encryption.encrypt(body.client_id)
    client_secret_enc = encryption.encrypt(body.client_secret)

    if cfg is None:
        import uuid as _uuid

        cfg = ProviderConfig(
            id=_uuid.uuid4(),
            provider_key=provider_key,
            auth_kind="oauth2",
            client_id_encrypted=client_id_enc,
            client_secret_encrypted=client_secret_enc,
            scopes=body.scopes,
            is_fallback=False,
        )
        session.add(cfg)
    else:
        cfg.client_id_encrypted = client_id_enc
        cfg.client_secret_encrypted = client_secret_enc
        if body.scopes is not None:
            cfg.scopes = body.scopes

    await session.commit()
    await session.refresh(cfg)

    return {
        "data": ProviderConfigResponse.from_model(cfg),
        "meta": {"request_id": request_id},
    }


@router.delete("/{provider_key}", status_code=204)
async def delete_provider_config(
    provider_key: str,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(ProviderConfig).where(ProviderConfig.provider_key == provider_key)
    )
    cfg = result.scalar_one_or_none()
    if cfg is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "provider_config_not_found", "message": "Provider config not found"},
        )

    await session.execute(delete(ProviderConfig).where(ProviderConfig.provider_key == provider_key))
    await session.commit()
