"""Shared provider config endpoint orchestration flows - Hosted version."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import HTTPException
from omnidapter_server.encryption import EncryptionService
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_hosted.schemas.provider_config import (
    ProviderConfigResponse,
    UpsertProviderConfigRequest,
)

ProviderConfigLike = Any
LoadConfig = Callable[[str, AsyncSession], Awaitable[ProviderConfigLike | None]]
ListConfigs = Callable[[AsyncSession], Awaitable[list[ProviderConfigLike]]]
CreateConfig = Callable[
    [str, str, str, list[str] | None],
    ProviderConfigLike,
]
DeleteConfig = Callable[[str, AsyncSession], Awaitable[None]]


def to_provider_config_response(cfg: ProviderConfigLike) -> ProviderConfigResponse:
    return ProviderConfigResponse(
        id=str(cfg.id),
        provider_key=cfg.provider_key,
        auth_kind=cfg.auth_kind,
        scopes=cfg.scopes,
        is_fallback=bool(getattr(cfg, "is_fallback", False)),
        is_enabled=getattr(cfg, "is_enabled", None),
        created_at=cfg.created_at,
        updated_at=cfg.updated_at,
    )


async def list_provider_configs_flow(
    *,
    session: AsyncSession,
    list_configs: ListConfigs,
) -> list[ProviderConfigResponse]:
    return [to_provider_config_response(c) for c in await list_configs(session)]


async def get_provider_config_flow(
    *,
    provider_key: str,
    session: AsyncSession,
    load_config: LoadConfig,
) -> ProviderConfigResponse:
    cfg = await load_config(provider_key, session)
    if cfg is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "provider_config_not_found", "message": "Provider config not found"},
        )
    return to_provider_config_response(cfg)


async def upsert_provider_config_flow(
    *,
    provider_key: str,
    body: UpsertProviderConfigRequest,
    encryption: EncryptionService,
    session: AsyncSession,
    load_config: LoadConfig,
    create_config: CreateConfig,
) -> ProviderConfigResponse:
    cfg = await load_config(provider_key, session)

    try:
        client_id_enc = encryption.encrypt(body.client_id)
        client_secret_enc = encryption.encrypt(body.client_secret)
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "encryption_not_configured",
                "message": "Encryption key is not configured or invalid",
            },
        ) from exc

    if cfg is None:
        cfg = create_config(provider_key, client_id_enc, client_secret_enc, body.scopes)
        session.add(cfg)
    else:
        cfg.client_id_encrypted = client_id_enc
        cfg.client_secret_encrypted = client_secret_enc
        if body.scopes is not None:
            cfg.scopes = body.scopes

    await session.commit()
    await session.refresh(cfg)
    return to_provider_config_response(cfg)


async def delete_provider_config_flow(
    *,
    provider_key: str,
    session: AsyncSession,
    load_config: LoadConfig,
    delete_config: DeleteConfig,
) -> None:
    cfg = await load_config(provider_key, session)
    if cfg is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "provider_config_not_found", "message": "Provider config not found"},
        )

    await delete_config(provider_key, session)
    await session.commit()
