"""Provider management endpoint — GET /v1/providers.

Returns all platform-supported providers with per-tenant configuration status.
Used by the org's admin UI to manage provider setup and enable/disable decisions.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from omnidapter import Omnidapter
from omnidapter.core.registry import ProviderRegistry
from omnidapter_server.database import get_session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_hosted.config import HostedSettings, get_hosted_settings
from omnidapter_hosted.dependencies import (
    HostedAuthContext,
    get_hosted_auth_context,
    get_request_id,
)
from omnidapter_hosted.models.provider_config import HostedProviderConfig

router = APIRouter(prefix="/providers", tags=["providers"])


def _has_fallback(provider_key: str, settings: HostedSettings) -> bool:
    """Return True if the server has hosted fallback credentials for this provider."""
    if provider_key == "google":
        return bool(
            settings.omnidapter_google_client_id and settings.omnidapter_google_client_secret
        )
    if provider_key == "microsoft":
        return bool(
            settings.omnidapter_microsoft_client_id and settings.omnidapter_microsoft_client_secret
        )
    if provider_key == "zoho":
        return bool(settings.omnidapter_zoho_client_id and settings.omnidapter_zoho_client_secret)
    return False


def _config_status(
    provider_key: str,
    auth_kind: str,
    config: HostedProviderConfig | None,
    fallback_available: bool,
) -> str:
    """Derive the config_status string for the management response."""
    if auth_kind != "oauth2":
        # Non-OAuth providers (CalDAV, Apple) need no OAuth app — always "configured"
        return "configured"
    if config is not None and config.client_id_encrypted and config.client_secret_encrypted:
        return "configured"
    if fallback_available:
        return "fallback"
    return "not_configured"


def _effective_is_enabled(
    config: HostedProviderConfig | None,
    auth_kind: str,
    fallback_available: bool,
) -> bool:
    """Return the effective is_enabled for a provider.

    If a config record exists, use its is_enabled flag.
    Otherwise, default to True if the provider can be used (fallback or non-OAuth).
    """
    if config is not None:
        return config.is_enabled
    # No explicit config: enabled if there's something to use
    if auth_kind != "oauth2":
        return True  # non-OAuth providers are self-service by default
    return fallback_available  # OAuth: enabled only when fallback exists


async def _load_tenant_configs(
    session: AsyncSession, tenant_id: uuid.UUID
) -> dict[str, HostedProviderConfig]:
    result = await session.execute(
        select(HostedProviderConfig).where(HostedProviderConfig.tenant_id == tenant_id)
    )
    return {cfg.provider_key: cfg for cfg in result.scalars().all()}


@router.get("")
async def list_providers_management(
    auth: Annotated[HostedAuthContext, Depends(get_hosted_auth_context)],
    session: AsyncSession = Depends(get_session),
    settings: HostedSettings = Depends(get_hosted_settings),
    request_id: str = Depends(get_request_id),
):
    """Return all platform-supported providers with per-tenant configuration status.

    Used by the admin dashboard to manage which providers are enabled and how
    they are configured (own OAuth app vs hosted fallback).
    """
    registry = ProviderRegistry()
    registry.register_builtins(auto_register_by_env=False)
    omni = Omnidapter(registry=registry)
    tenant_configs = await _load_tenant_configs(session, auth.tenant_id)

    data = []
    for provider_key in omni.list_providers():
        meta = omni.describe_provider(provider_key)
        auth_kind = meta.auth_kinds[0].value if meta.auth_kinds else "oauth2"
        config = tenant_configs.get(provider_key)
        fallback_available = _has_fallback(provider_key, settings)

        data.append(
            {
                "provider_key": provider_key,
                "display_name": meta.display_name,
                "auth_kind": auth_kind,
                "config_status": _config_status(
                    provider_key, auth_kind, config, fallback_available
                ),
                "is_enabled": _effective_is_enabled(config, auth_kind, fallback_available),
                "fallback_available": fallback_available,
            }
        )

    return {"data": data, "meta": {"request_id": request_id}}
