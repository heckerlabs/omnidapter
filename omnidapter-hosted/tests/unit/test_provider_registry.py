"""Unit tests for hosted provider registry composition."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from omnidapter_hosted.models.provider_config import HostedProviderConfig
from omnidapter_hosted.services.provider_registry import build_hosted_provider_registry
from omnidapter_server.config import Settings
from omnidapter_server.encryption import EncryptionService


@pytest.mark.asyncio
async def test_build_hosted_provider_registry_without_provider_uses_server_registry() -> None:
    with patch(
        "omnidapter_hosted.services.provider_registry.build_provider_registry",
        return_value="registry",
    ) as build_registry:
        result = await build_hosted_provider_registry(
            tenant_id=uuid.uuid4(),
            provider_key=None,
            session=AsyncMock(),
            settings=Settings(),
            encryption=EncryptionService(
                current_key="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
            ),
        )

    assert result == "registry"
    build_registry.assert_called_once()


@pytest.mark.asyncio
async def test_build_hosted_provider_registry_without_tenant_config_falls_back() -> None:
    with (
        patch(
            "omnidapter_hosted.services.provider_registry.get_tenant_provider_config",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "omnidapter_hosted.services.provider_registry.build_provider_registry",
            return_value="fallback-registry",
        ) as build_registry,
    ):
        result = await build_hosted_provider_registry(
            tenant_id=uuid.uuid4(),
            provider_key="google",
            session=AsyncMock(),
            settings=Settings(),
            encryption=EncryptionService(
                current_key="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
            ),
        )

    assert result == "fallback-registry"
    build_registry.assert_called_once()


@pytest.mark.asyncio
async def test_build_hosted_provider_registry_with_tenant_config_applies_override() -> None:
    cfg = HostedProviderConfig(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        provider_key="google",
        auth_kind="oauth2",
        client_id_encrypted="enc-id",
        client_secret_encrypted="enc-secret",
        scopes=None,
    )
    encryption = EncryptionService(current_key="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
    with (
        patch(
            "omnidapter_hosted.services.provider_registry.get_tenant_provider_config",
            new=AsyncMock(return_value=cfg),
        ),
        patch.object(
            encryption, "decrypt", side_effect=["tenant-client-id", "tenant-client-secret"]
        ),
    ):
        registry = await build_hosted_provider_registry(
            tenant_id=cfg.tenant_id,
            provider_key="google",
            session=AsyncMock(),
            settings=Settings(),
            encryption=encryption,
        )

    oauth = registry.get("google").get_oauth_config()
    assert oauth is not None
    assert oauth.client_id == "tenant-client-id"
    assert oauth.client_secret == "tenant-client-secret"
