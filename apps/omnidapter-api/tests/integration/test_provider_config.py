"""Integration tests for provider config CRUD."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from omnidapter_api.encryption import EncryptionService
from omnidapter_api.models.organization import Organization
from omnidapter_api.models.provider_config import ProviderConfig
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
    org: Organization,
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
    org: Organization,
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
            ProviderConfig.organization_id == org.id,
            ProviderConfig.provider_key == "microsoft",
        )
    )
    cfg = result.scalar_one_or_none()
    assert cfg is not None
    # Verify stored value is encrypted (not plaintext)
    assert cfg.client_id_encrypted != "ms-client-id"
    assert cfg.client_secret_encrypted != "ms-secret"
    assert cfg.client_id_encrypted is not None
    assert cfg.client_secret_encrypted is not None
    # But can be decrypted
    assert encryption.decrypt(cfg.client_id_encrypted) == "ms-client-id"
    assert encryption.decrypt(cfg.client_secret_encrypted) == "ms-secret"


@pytest.mark.asyncio
async def test_get_provider_config(
    client: AsyncClient,
    session: AsyncSession,
    org: Organization,
    encryption: EncryptionService,
):
    import uuid

    cfg = ProviderConfig(
        id=uuid.uuid4(),
        organization_id=org.id,
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
    org: Organization,
    encryption: EncryptionService,
):
    import uuid

    cfg = ProviderConfig(
        id=uuid.uuid4(),
        organization_id=org.id,
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
    org: Organization,
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


@pytest.mark.asyncio
async def test_org_isolation_provider_configs(
    client: AsyncClient,
    session: AsyncSession,
):
    """Org B cannot see Org A's provider configs."""
    from omnidapter_api.models.organization import Organization

    other_org = Organization(
        id=__import__("uuid").uuid4(), name="Other Org", plan="free", is_active=True
    )
    session.add(other_org)
    await session.flush()

    cfg = ProviderConfig(
        id=__import__("uuid").uuid4(),
        organization_id=other_org.id,
        provider_key="google",
        auth_kind="oauth2",
        is_fallback=False,
    )
    session.add(cfg)
    await session.flush()

    # Our client (different org) should not see this
    response = await client.get("/v1/provider-configs")
    assert len(response.json()["data"]) == 0
