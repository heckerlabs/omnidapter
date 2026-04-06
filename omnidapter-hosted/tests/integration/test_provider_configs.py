"""Integration tests for provider configuration management and tenant isolation."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from omnidapter_hosted.models.api_key import HostedAPIKey
from omnidapter_hosted.models.provider_config import HostedProviderConfig
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_provider_configs_isolation(
    client: AsyncClient,
    db_session: AsyncSession,
    test_api_key: tuple[str, HostedAPIKey],
    second_api_key: tuple[str, HostedAPIKey],
):
    """Verify that Tenant A cannot see Tenant B's provider configurations."""
    raw_key_a, _ = test_api_key
    raw_key_b, _ = second_api_key

    # List as Tenant A (should see google from conftest fixture)
    response = await client.get(
        "/v1/provider-configs", headers={"Authorization": f"Bearer {raw_key_a}"}
    )
    assert response.status_code == 200
    keys = [c["provider_key"] for c in response.json()["data"]]
    assert "google" in keys

    # Add a second config for Tenant A
    config_a_2 = HostedProviderConfig(
        id=uuid.uuid4(),
        tenant_id=test_api_key[1].tenant_id,
        provider_key="microsoft",
        auth_kind="oauth2",
        is_enabled=True,
    )
    db_session.add(config_a_2)
    await db_session.flush()

    # List as Tenant A (should see google and microsoft)
    response = await client.get(
        "/v1/provider-configs", headers={"Authorization": f"Bearer {raw_key_a}"}
    )
    assert response.status_code == 200
    keys = [c["provider_key"] for c in response.json()["data"]]
    assert "google" in keys
    assert "microsoft" in keys

    # List as Tenant B (should see 0, or just its own if it has any)
    # second_tenant fixture doesn't add any configs.
    response = await client.get(
        "/v1/provider-configs", headers={"Authorization": f"Bearer {raw_key_b}"}
    )
    assert response.status_code == 200
    assert len(response.json()["data"]) == 0


@pytest.mark.asyncio
async def test_upsert_provider_config_isolation(
    client: AsyncClient,
    db_session: AsyncSession,
    test_api_key: tuple[str, HostedAPIKey],
    second_api_key: tuple[str, HostedAPIKey],
):
    """Verify that Tenant B cannot upsert Tenant A's provider configuration."""
    raw_key_b, _ = second_api_key

    # Attempt to upsert for Tenant A's provider key (google)
    # But wait! Tenant B has its OWN google config space.
    # To test isolation, we check if Tenant B's change affects Tenant A.

    # 1. Update Tenant B's google config to enabled=False
    response = await client.patch(
        "/v1/provider-configs/google",
        json={"is_enabled": False},
        headers={"Authorization": f"Bearer {raw_key_b}"},
    )
    assert response.status_code == 200

    # 2. Check Tenant A's google config (should still be True from conftest)
    raw_key_a, _ = test_api_key
    response = await client.get(
        "/v1/provider-configs/google", headers={"Authorization": f"Bearer {raw_key_a}"}
    )
    assert response.status_code == 200
    assert response.json()["data"]["is_enabled"] is True
