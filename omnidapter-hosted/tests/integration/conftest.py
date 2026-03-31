"""Integration test configuration for omnidapter-hosted — Function-scoped to avoid loop issues."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from omnidapter_hosted.config import HostedSettings
from omnidapter_hosted.database import HostedBase
from omnidapter_hosted.main import create_app
from omnidapter_hosted.models.api_key import HostedAPIKey
from omnidapter_hosted.models.provider_config import HostedProviderConfig
from omnidapter_hosted.models.tenant import Tenant, TenantPlan
from omnidapter_hosted.services.auth import generate_hosted_api_key
from omnidapter_hosted.services.billing import _redis_clients
from omnidapter_server.database import get_session
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine


def pytest_configure(config: pytest.Config) -> None:
    """Set up integration test environment variables."""
    os.environ["OMNIDAPTER_ENV"] = "DEV"
    os.environ["OMNIDAPTER_DATABASE_URL"] = (
        "postgresql+asyncpg://omnidapter:omnidapter@localhost:5432/omnidapter"
    )
    os.environ["HOSTED_RATE_LIMIT_REDIS_URL"] = "redis://localhost:6379/1"
    os.environ["OMNIDAPTER_ENCRYPTION_KEY"] = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="


@pytest.fixture(scope="session", autouse=True)
def skip_if_no_integration():
    """Skip integration tests unless OMNIDAPTER_INTEGRATION=1 is set."""
    if os.environ.get("OMNIDAPTER_INTEGRATION") != "1":
        pytest.skip("Set OMNIDAPTER_INTEGRATION=1 to run integration tests")


@pytest_asyncio.fixture(autouse=True)
async def clear_redis_clients():
    _redis_clients.clear()
    yield
    _redis_clients.clear()


@pytest_asyncio.fixture
async def db_engine() -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(os.environ["OMNIDAPTER_DATABASE_URL"])
    async with engine.begin() as conn:
        await conn.run_sync(HostedBase.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a database session that rolls back after each test."""
    async with db_engine.connect() as conn:
        await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        yield session
        await session.rollback()
        await session.close()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Provide an HTTP client for testing the FastAPI app."""

    async def _get_session_override():
        yield db_session

    # Force a very low rate limit for testing
    test_settings = HostedSettings()
    test_settings.hosted_rate_limit_free = 2
    test_settings.hosted_rate_limit_paid = 2
    test_settings.omnidapter_google_client_id = "test-google-id"
    test_settings.omnidapter_google_client_secret = "test-google-secret"

    app = create_app(settings=test_settings)
    app.dependency_overrides[get_session] = _get_session_override

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_tenant(db_session: AsyncSession) -> Tenant:
    """Create a test tenant and enable a provider."""
    tenant = Tenant(id=uuid.uuid4(), name="Test Tenant", plan=TenantPlan.FREE, is_active=True)
    db_session.add(tenant)
    await db_session.flush()  # Flush parent first to avoid FK violation

    # Enable google provider for this tenant
    provider_config = HostedProviderConfig(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        provider_key="google",
        auth_kind="oauth2",
        is_enabled=True,
    )
    db_session.add(provider_config)

    await db_session.flush()
    return tenant


@pytest_asyncio.fixture
async def test_api_key(db_session: AsyncSession, test_tenant: Tenant) -> tuple[str, HostedAPIKey]:
    """Create a test API key for the test tenant."""
    raw_key, key_hash, key_prefix = generate_hosted_api_key()
    api_key = HostedAPIKey(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        name="Test Key",
        key_hash=key_hash,
        key_prefix=key_prefix,
    )
    db_session.add(api_key)
    await db_session.flush()
    return raw_key, api_key


@pytest_asyncio.fixture
async def second_tenant(db_session: AsyncSession) -> Tenant:
    """Create a second test tenant for isolation testing."""
    tenant = Tenant(id=uuid.uuid4(), name="Second Tenant", plan=TenantPlan.FREE, is_active=True)
    db_session.add(tenant)
    await db_session.flush()
    return tenant


@pytest_asyncio.fixture
async def second_api_key(
    db_session: AsyncSession, second_tenant: Tenant
) -> tuple[str, HostedAPIKey]:
    """Create an API key for the second tenant."""
    raw_key, key_hash, key_prefix = generate_hosted_api_key()
    api_key = HostedAPIKey(
        id=uuid.uuid4(),
        tenant_id=second_tenant.id,
        name="Second Key",
        key_hash=key_hash,
        key_prefix=key_prefix,
    )
    db_session.add(api_key)
    await db_session.flush()
    return raw_key, api_key
