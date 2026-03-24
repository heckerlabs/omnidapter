"""Hosted provider registry helpers."""

from __future__ import annotations

import uuid
from typing import Any, cast

from omnidapter.core.registry import ProviderRegistry
from omnidapter_server.config import Settings
from omnidapter_server.encryption import EncryptionService
from omnidapter_server.provider_registry import build_provider_registry
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_hosted.services.tenant_resources import get_tenant_provider_config


class _ProviderConfigOverride:
    def __init__(
        self,
        *,
        provider_key: str,
        client_id_encrypted: str,
        client_secret_encrypted: str,
    ) -> None:
        self.provider_key = provider_key
        self.is_fallback = False
        self.client_id_encrypted = client_id_encrypted
        self.client_secret_encrypted = client_secret_encrypted


async def build_hosted_provider_registry(
    *,
    tenant_id: uuid.UUID,
    provider_key: str | None,
    session: AsyncSession,
    settings: Settings,
    encryption: EncryptionService,
) -> ProviderRegistry:
    if provider_key is None:
        return build_provider_registry(settings=settings)

    tenant_cfg = await get_tenant_provider_config(
        session=session,
        tenant_id=tenant_id,
        provider_key=provider_key,
    )
    if tenant_cfg is None:
        return build_provider_registry(settings=settings)

    # Treat missing encrypted credentials as "no valid override configured" — fall
    # back to server-level credentials rather than passing empty strings that would
    # fail decryption downstream.
    if not tenant_cfg.client_id_encrypted or not tenant_cfg.client_secret_encrypted:
        return build_provider_registry(settings=settings)

    override = _ProviderConfigOverride(
        provider_key=tenant_cfg.provider_key,
        client_id_encrypted=tenant_cfg.client_id_encrypted,
        client_secret_encrypted=tenant_cfg.client_secret_encrypted,
    )
    return build_provider_registry(
        settings=settings,
        provider_config=cast(Any, override),
        encryption=encryption,
    )
