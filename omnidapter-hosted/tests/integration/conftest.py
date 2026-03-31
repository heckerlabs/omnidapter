"""Integration test fixtures with real Postgres and Redis via Testcontainers."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from omnidapter_hosted.config import HostedSettings
from omnidapter_hosted.database import HostedBase
from omnidapter_hosted.main import create_app
from omnidapter_hosted.models.api_key import HostedAPIKey
from omnidapter_hosted.models.membership import HostedMembership, MemberRole
from omnidapter_hosted.models.provider_config import HostedProviderConfig
from omnidapter_hosted.models.tenant import Tenant, TenantPlan
from omnidapter_hosted.models.user import HostedUser
from omnidapter_hosted.services.auth import generate_hosted_api_key
from omnidapter_hosted.services.auth_flows import issue_jwt
from omnidapter_hosted.services.billing import _redis_clients
from omnidapter_server.database import Base, get_session
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer


@pytest.fixture(scope="session")
def postgres_url() -> Generator[str, None, None]:
    """Start a Postgres container for the test session."""
    with PostgresContainer("postgres:16-alpine") as postgres:
        yield postgres.get_connection_url().replace("psycopg2", "asyncpg")


@pytest.fixture(scope="session")
def redis_url() -> Generator[str, None, None]:
    """Start a Redis container for the test session."""
    with RedisContainer("redis:7-alpine") as redis:
        host = redis.get_container_host_ip()
        port = redis.get_exposed_port(6379)
        yield f"redis://{host}:{port}/1"


@pytest_asyncio.fixture(autouse=True)
async def clear_redis_clients():
    _redis_clients.clear()
    yield
    _redis_clients.clear()


@pytest_asyncio.fixture
async def db_engine(postgres_url: str) -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(postgres_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
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
async def client(
    db_session: AsyncSession, postgres_url: str, redis_url: str
) -> AsyncGenerator[AsyncClient, None]:
    """Provide an HTTP client for testing the FastAPI app."""

    async def _get_session_override():
        yield db_session

    # Force a very low rate limit for testing
    test_settings = HostedSettings()
    test_settings.hosted_rate_limit_free = 2
    test_settings.hosted_rate_limit_paid = 2
    test_settings.omnidapter_google_client_id = "test-google-id"
    test_settings.omnidapter_google_client_secret = "test-google-secret"
    test_settings.omnidapter_database_url = postgres_url
    test_settings.hosted_rate_limit_redis_url = redis_url

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


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> HostedUser:
    """Create a test user."""
    user = HostedUser(
        id=uuid.uuid4(),
        email=f"test-{uuid.uuid4().hex[:8]}@example.com",
        name="Test User",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def test_membership(
    db_session: AsyncSession, test_user: HostedUser, test_tenant: Tenant
) -> HostedMembership:
    """Create a membership for the test user in the test tenant."""
    membership = HostedMembership(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        user_id=test_user.id,
        role=MemberRole.OWNER,
    )
    db_session.add(membership)
    await db_session.flush()
    return membership


@pytest.fixture
def dashboard_auth(test_user: HostedUser, test_tenant: Tenant, test_membership: HostedMembership):
    """Return a valid dashboard JWT for the test user/tenant/membership."""

    class _JWTContext:
        def __init__(self, user, tenant, membership):
            self.user = user
            self.tenant = tenant
            self.membership = membership

        def get_token(self, settings) -> str:
            return issue_jwt(self.user.id, self.tenant.id, self.membership.role, settings)

    return _JWTContext(test_user, test_tenant, test_membership)


@pytest_asyncio.fixture
async def dashboard_client(
    db_session: AsyncSession, postgres_url: str, redis_url: str, dashboard_auth
) -> AsyncGenerator[AsyncClient, None]:
    """Provide an HTTP client for testing the dashboard endpoints (authenticated via JWT)."""

    async def _get_session_override():
        yield db_session

    test_settings = HostedSettings()
    test_settings.omnidapter_database_url = postgres_url
    test_settings.hosted_rate_limit_redis_url = redis_url
    test_settings.jwt_secret = "a" * 32

    app = create_app(settings=test_settings)
    app.dependency_overrides[get_session] = _get_session_override

    token = dashboard_auth.get_token(test_settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        ac.headers["Authorization"] = f"Bearer {token}"
        yield ac

    app.dependency_overrides.clear()
