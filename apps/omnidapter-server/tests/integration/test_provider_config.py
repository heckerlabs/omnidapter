"""Integration tests for provider config CRUD."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from omnidapter_server.encryption import EncryptionService
from omnidapter_server.models.provider_config import ProviderConfig
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_list_provider_configs_empty(client: AsyncClient):
    response = await client.get("/v1/provider-configs")
    assert response.status_code == 200
    assert response.json()["data"] == []


@pytest.mark.asyncio
async def test_upsert_provider_config(
    client: AsyncClient,
    session: AsyncSession,
):
    response = await client.put(
        "/v1/provider-configs/google",
        json={
            "client_id": "my-client-id",
            "client_secret": "my-client-secret",
            "scopes": ["https://www.googleapis.com/auth/calendar"],
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["provider_key"] == "google"
    assert data["is_fallback"] is False
    assert data["scopes"] == ["https://www.googleapis.com/auth/calendar"]


@pytest.mark.asyncio
async def test_provider_config_credentials_encrypted_in_db(
    client: AsyncClient,
    session: AsyncSession,
    encryption: EncryptionService,
):
    await client.put(
        "/v1/provider-configs/microsoft",
        json={
            "client_id": "ms-client-id",
            "client_secret": "ms-secret",
        },
    )

    from sqlalchemy import select

    result = await session.execute(
        select(ProviderConfig).where(
            ProviderConfig.provider_key == "microsoft",
        )
    )
    cfg = result.scalar_one_or_none()
    assert cfg is not None
    # Verify stored value is encrypted (not plaintext)
    assert cfg.client_id_encrypted != "ms-client-id"
    assert cfg.client_secret_encrypted != "ms-secret"
    # But can be decrypted
    assert cfg.client_id_encrypted is not None
    assert cfg.client_secret_encrypted is not None
    assert encryption.decrypt(cfg.client_id_encrypted) == "ms-client-id"
    assert encryption.decrypt(cfg.client_secret_encrypted) == "ms-secret"


@pytest.mark.asyncio
async def test_get_provider_config(
    client: AsyncClient,
    session: AsyncSession,
    encryption: EncryptionService,
):
    import uuid

    cfg = ProviderConfig(
        id=uuid.uuid4(),
        provider_key="zoho",
        auth_kind="oauth2",
        client_id_encrypted=encryption.encrypt("zoho-client-id"),
        client_secret_encrypted=encryption.encrypt("zoho-secret"),
        scopes=["ZohoCalendar.event.ALL"],
        is_fallback=False,
    )
    session.add(cfg)
    await session.flush()

    response = await client.get("/v1/provider-configs/zoho")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["provider_key"] == "zoho"
    assert data["scopes"] == ["ZohoCalendar.event.ALL"]


@pytest.mark.asyncio
async def test_get_provider_config_not_found(client: AsyncClient):
    response = await client.get("/v1/provider-configs/nonexistent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_provider_config(
    client: AsyncClient,
    session: AsyncSession,
    encryption: EncryptionService,
):
    import uuid

    cfg = ProviderConfig(
        id=uuid.uuid4(),
        provider_key="caldav",
        auth_kind="basic",
        is_fallback=False,
    )
    session.add(cfg)
    await session.flush()

    response = await client.delete("/v1/provider-configs/caldav")
    assert response.status_code == 204

    # Verify deleted
    response = await client.get("/v1/provider-configs/caldav")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_provider_config(
    client: AsyncClient,
    session: AsyncSession,
):
    # Create
    await client.put(
        "/v1/provider-configs/google",
        json={"client_id": "original-id", "client_secret": "original-secret"},
    )

    # Update
    response = await client.put(
        "/v1/provider-configs/google",
        json={"client_id": "updated-id", "client_secret": "updated-secret"},
    )
    assert response.status_code == 200

    # Verify only one record
    response = await client.get("/v1/provider-configs")
    assert len(response.json()["data"]) == 1
