"""Integration tests for global access — API keys are global, not org-scoped."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from omnidapter_server.models.api_key import APIKey
from omnidapter_server.models.connection import Connection, ConnectionStatus
from omnidapter_server.services.auth import generate_api_key
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

TEST_ENCRYPTION_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="


@pytest_asyncio.fixture
async def second_api_key(session: AsyncSession) -> tuple[str, APIKey]:
    """A second independent API key."""
    raw_key, key_hash, key_prefix = generate_api_key()
    key = APIKey(
        id=uuid.uuid4(),
        name="second-key",
        key_hash=key_hash,
        key_prefix=key_prefix,
        is_active=True,
        is_test=False,
    )
    session.add(key)
    await session.flush()
    return raw_key, key


@pytest_asyncio.fixture
async def second_client(
    session: AsyncSession,
    second_api_key: tuple[str, APIKey],
) -> AsyncIterator[AsyncClient]:
    """HTTP client authenticated with a second independent API key."""
    raw_key, _ = second_api_key

    from omnidapter_server.config import Settings, get_settings
    from omnidapter_server.database import get_session
    from omnidapter_server.dependencies import get_encryption_service
    from omnidapter_server.encryption import EncryptionService
    from omnidapter_server.main import app

    async def override_session():
        yield session

    def override_encryption():
        return EncryptionService(current_key=TEST_ENCRYPTION_KEY)

    def override_settings():
        return Settings(
            omnidapter_database_url="",
            omnidapter_encryption_key=TEST_ENCRYPTION_KEY,
            omnidapter_env="test",
        )

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_encryption_service] = override_encryption

    async with AsyncClient(transport=ASGITransport(app), base_url="http://testserver") as c:
        c.headers["Authorization"] = f"Bearer {raw_key}"
        yield c

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_two_keys_can_both_access_same_connection(
    client: AsyncClient,
    second_client: AsyncClient,
    session: AsyncSession,
):
    """Two different API keys can both read the same connection — access is global."""
    conn = Connection(
        id=uuid.uuid4(),
        provider_key="google",
        external_id="shared_user",
        status=ConnectionStatus.ACTIVE,
    )
    session.add(conn)
    await session.flush()

    response_a = await client.get(f"/v1/connections/{conn.id}")
    assert response_a.status_code == 200
    assert response_a.json()["data"]["id"] == str(conn.id)

    response_b = await second_client.get(f"/v1/connections/{conn.id}")
    assert response_b.status_code == 200
    assert response_b.json()["data"]["id"] == str(conn.id)


@pytest.mark.asyncio
async def test_two_keys_can_both_list_all_connections(
    client: AsyncClient,
    second_client: AsyncClient,
    session: AsyncSession,
):
    """Both API keys see all connections in the global list."""
    conn1 = Connection(
        id=uuid.uuid4(),
        provider_key="google",
        external_id="global_user_1",
        status=ConnectionStatus.ACTIVE,
    )
    conn2 = Connection(
        id=uuid.uuid4(),
        provider_key="microsoft",
        external_id="global_user_2",
        status=ConnectionStatus.ACTIVE,
    )
    session.add(conn1)
    session.add(conn2)
    await session.flush()

    response_a = await client.get("/v1/connections")
    assert response_a.status_code == 200
    ids_a = {c["id"] for c in response_a.json()["data"]}
    assert str(conn1.id) in ids_a
    assert str(conn2.id) in ids_a

    response_b = await second_client.get("/v1/connections")
    assert response_b.status_code == 200
    ids_b = {c["id"] for c in response_b.json()["data"]}
    assert str(conn1.id) in ids_b
    assert str(conn2.id) in ids_b


@pytest.mark.asyncio
async def test_unauthenticated_request_rejected(client: AsyncClient):
    """Requests without a valid API key are rejected with 401."""
    from omnidapter_server.config import Settings, get_settings
    from omnidapter_server.dependencies import get_encryption_service
    from omnidapter_server.encryption import EncryptionService
    from omnidapter_server.main import app

    # We need a fresh client with no auth header
    async def override_session():
        from tests.integration.conftest import get_test_factory  # noqa: PLC0415

        async with get_test_factory()() as s:
            yield s

    def override_encryption():
        return EncryptionService(current_key=TEST_ENCRYPTION_KEY)

    def override_settings():
        return Settings(
            omnidapter_database_url="",
            omnidapter_encryption_key=TEST_ENCRYPTION_KEY,
            omnidapter_env="test",
        )

    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_encryption_service] = override_encryption

    try:
        async with AsyncClient(
            transport=ASGITransport(app), base_url="http://testserver"
        ) as anon_client:
            response = await anon_client.get("/v1/connections")
        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_external_id_globally_unique_per_provider(
    session: AsyncSession,
):
    """Two connections with the same provider and external_id cannot coexist."""
    ext_id = "duplicate_external_id"

    conn1 = Connection(
        id=uuid.uuid4(),
        provider_key="google",
        external_id=ext_id,
        status=ConnectionStatus.ACTIVE,
    )
    session.add(conn1)
    await session.flush()

    from sqlalchemy.exc import IntegrityError

    conn2 = Connection(
        id=uuid.uuid4(),
        provider_key="google",
        external_id=ext_id,
        status=ConnectionStatus.ACTIVE,
    )
    session.add(conn2)
    with pytest.raises(IntegrityError):
        await session.flush()
