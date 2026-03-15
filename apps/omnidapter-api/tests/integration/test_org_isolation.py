"""Integration tests for organization isolation."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from omnidapter_api.models.api_key import APIKey
from omnidapter_api.models.connection import Connection, ConnectionStatus
from omnidapter_api.models.organization import Organization
from omnidapter_api.models.provider_config import ProviderConfig
from omnidapter_api.services.auth import generate_api_key
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def org_b(session: AsyncSession) -> Organization:
    org = Organization(id=uuid.uuid4(), name="Org B", plan="free", is_active=True)
    session.add(org)
    await session.flush()
    return org


@pytest_asyncio.fixture
async def client_b(session: AsyncSession, org_b: Organization) -> AsyncIterator[AsyncClient]:
    """HTTP client authenticated as Org B."""
    raw_key, key_hash, key_prefix = generate_api_key()
    key = APIKey(
        id=uuid.uuid4(),
        organization_id=org_b.id,
        name="org-b-key",
        key_hash=key_hash,
        key_prefix=key_prefix,
        is_active=True,
    )
    session.add(key)
    await session.flush()

    from omnidapter_api.config import Settings, get_settings
    from omnidapter_api.database import get_session
    from omnidapter_api.dependencies import get_encryption_service
    from omnidapter_api.encryption import EncryptionService
    from omnidapter_api.main import app

    async def override_session():
        yield session

    def override_encryption():
        return EncryptionService(current_key="dGVzdC1lbmNyeXB0aW9uLWtleS1pbnRlZ3JhdGlvbiEh")

    def override_settings():
        return Settings(
            omnidapter_database_url="",
            omnidapter_encryption_key="dGVzdC1lbmNyeXB0aW9uLWtleS1pbnRlZ3JhdGlvbiEh",
            omnidapter_env="test",
        )

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_encryption_service] = override_encryption

    from httpx import AsyncClient

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        c.headers["Authorization"] = f"Bearer {raw_key}"
        yield c

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_org_b_cannot_see_org_a_connections(
    client: AsyncClient,
    client_b: AsyncClient,
    session: AsyncSession,
    org: Organization,
):
    """Org B's client cannot list Org A's connections."""
    conn = Connection(
        id=uuid.uuid4(),
        organization_id=org.id,
        provider_key="google",
        external_id="org_a_user",
        status=ConnectionStatus.ACTIVE,
    )
    session.add(conn)
    await session.flush()

    # Org A sees its own connection
    response_a = await client.get("/v1/connections")
    assert any(c["id"] == str(conn.id) for c in response_a.json()["data"])

    # Org B sees nothing
    response_b = await client_b.get("/v1/connections")
    assert not any(c["id"] == str(conn.id) for c in response_b.json()["data"])


@pytest.mark.asyncio
async def test_org_b_cannot_access_org_a_connection_by_id(
    client_b: AsyncClient,
    session: AsyncSession,
    org: Organization,
):
    """Org B gets 404 when trying to access Org A's connection by ID."""
    conn = Connection(
        id=uuid.uuid4(),
        organization_id=org.id,
        provider_key="google",
        external_id="org_a_private",
        status=ConnectionStatus.ACTIVE,
    )
    session.add(conn)
    await session.flush()

    response = await client_b.get(f"/v1/connections/{conn.id}")
    assert response.status_code == 404  # Not 403 — don't leak existence


@pytest.mark.asyncio
async def test_org_b_cannot_see_org_a_provider_configs(
    client_b: AsyncClient,
    session: AsyncSession,
    org: Organization,
):
    """Org B cannot see Org A's provider configs."""
    cfg = ProviderConfig(
        id=uuid.uuid4(),
        organization_id=org.id,
        provider_key="google",
        auth_kind="oauth2",
        is_fallback=False,
    )
    session.add(cfg)
    await session.flush()

    response = await client_b.get("/v1/provider-configs")
    assert len(response.json()["data"]) == 0


@pytest.mark.asyncio
async def test_external_id_unique_within_org_but_reusable_across_orgs(
    session: AsyncSession,
    org: Organization,
    org_b: Organization,
):
    """external_id must be unique per org but can be reused across orgs."""
    ext_id = "shared_external_id"

    conn_a = Connection(
        id=uuid.uuid4(),
        organization_id=org.id,
        provider_key="google",
        external_id=ext_id,
        status=ConnectionStatus.ACTIVE,
    )
    conn_b = Connection(
        id=uuid.uuid4(),
        organization_id=org_b.id,
        provider_key="google",
        external_id=ext_id,  # Same external_id, different org — should be OK
        status=ConnectionStatus.ACTIVE,
    )
    session.add(conn_a)
    session.add(conn_b)
    # Should not raise UniqueConstraint violation
    await session.flush()
