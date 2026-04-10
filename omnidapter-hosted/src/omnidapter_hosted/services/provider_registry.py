"""Hosted provider registry helpers."""

from __future__ import annotations

import uuid

from omnidapter.core.registry import ProviderRegistry
from omnidapter.providers.google.provider import GoogleProvider
from omnidapter.providers.microsoft.provider import MicrosoftProvider
from omnidapter.providers.zoho.provider import ZohoProvider
from omnidapter_server.config import Settings
from omnidapter_server.encryption import EncryptionService
from omnidapter_server.provider_registry import build_provider_registry
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_hosted.services.tenant_resources import get_tenant_provider_config

_OAUTH_PROVIDER_FACTORIES = {
    "google": GoogleProvider,
    "microsoft": MicrosoftProvider,
    "zoho": ZohoProvider,
}


async def build_hosted_provider_registry(
    *,
    tenant_id: uuid.UUID,
    provider_key: str | None,
    session: AsyncSession,
    settings: Settings,
    encryption: EncryptionService,
) -> ProviderRegistry:
    registry = build_provider_registry(settings=settings)

    if provider_key is None:
        return registry

    tenant_cfg = await get_tenant_provider_config(
        session=session,
        tenant_id=tenant_id,
        provider_key=provider_key,
    )
    if tenant_cfg is None:
        return registry

    if not tenant_cfg.client_id_encrypted or not tenant_cfg.client_secret_encrypted:
        return registry

    provider_factory = _OAUTH_PROVIDER_FACTORIES.get(tenant_cfg.provider_key)
    if provider_factory is None:
        return registry

    registry.replace(
        provider_factory(
            client_id=encryption.decrypt(tenant_cfg.client_id_encrypted),
            client_secret=encryption.decrypt(tenant_cfg.client_secret_encrypted),
        )
    )
    return registry
