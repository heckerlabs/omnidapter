"""Integration test fixtures with real Postgres database.

Integration tests are skipped when OMNIDAPTER_INTEGRATION=1 is not set
or when the test database is unavailable.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from omnidapter_api.database import Base, get_session
from omnidapter_api.encryption import EncryptionService
from omnidapter_api.main import app
from omnidapter_api.models.api_key import APIKey
from omnidapter_api.models.organization import Organization
from omnidapter_api.services.auth import generate_api_key
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DB_URL = os.environ.get(
    "OMNIDAPTER_TEST_DATABASE_URL",
    "postgresql+asyncpg://localhost/omnidapter_test",
)

# Skip integration tests when DB is not available or OMNIDAPTER_INTEGRATION not set
_SKIP_INTEGRATION = not bool(os.environ.get("OMNIDAPTER_INTEGRATION"))
TEST_ENCRYPTION_KEY = "test-encryption-key-integration-tests"

_test_engine = None
_test_factory = None


def get_test_engine():
    global _test_engine
    if _test_engine is None:
        _test_engine = create_async_engine(TEST_DB_URL, echo=False)
    return _test_engine


def get_test_factory():
    global _test_factory
    if _test_factory is None:
        _test_factory = async_sessionmaker(
            get_test_engine(), class_=AsyncSession, expire_on_commit=False
        )
    return _test_factory


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session", autouse=True)
def skip_if_no_integration():
    if _SKIP_INTEGRATION:
        pytest.skip("Set OMNIDAPTER_INTEGRATION=1 to run integration tests")


@pytest_asyncio.fixture(scope="session")
async def setup_database():
    """Create tables once per session."""
    engine = get_test_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def session(setup_database) -> AsyncIterator[AsyncSession]:
    """Provide a transactional session that rolls back after each test."""
    engine = get_test_engine()
    async with engine.begin() as conn:
        # Use nested transaction for rollback
        session = AsyncSession(bind=conn, expire_on_commit=False)
        yield session
        await session.rollback()
        await session.close()


@pytest.fixture
def encryption() -> EncryptionService:
    return EncryptionService(current_key=TEST_ENCRYPTION_KEY)


@pytest_asyncio.fixture
async def org(session: AsyncSession) -> Organization:
    """Create a test organization."""
    org = Organization(
        id=uuid.uuid4(),
        name="Test Organization",
        plan="free",
        is_active=True,
    )
    session.add(org)
    await session.flush()
    return org


@pytest_asyncio.fixture
async def api_key(session: AsyncSession, org: Organization) -> tuple[str, APIKey]:
    """Create a test API key, returning (raw_key, APIKey)."""
    raw_key, key_hash, key_prefix = generate_api_key()
    key = APIKey(
        id=uuid.uuid4(),
        organization_id=org.id,
        name="test",
        key_hash=key_hash,
        key_prefix=key_prefix,
        is_active=True,
    )
    session.add(key)
    await session.flush()
    return raw_key, key


@pytest_asyncio.fixture
async def client(session: AsyncSession, api_key: tuple[str, APIKey]) -> AsyncIterator[AsyncClient]:
    """HTTP test client with API key auth and injected test session."""
    raw_key, _ = api_key

    # Override the session dependency
    async def override_session():
        yield session

    # Override settings for test encryption key
    from omnidapter_api.config import Settings, get_settings
    from omnidapter_api.dependencies import get_encryption_service

    def override_encryption():
        return EncryptionService(current_key=TEST_ENCRYPTION_KEY)

    def override_settings():
        settings = Settings(
            omnidapter_database_url=TEST_DB_URL,
            omnidapter_encryption_key=TEST_ENCRYPTION_KEY,
            omnidapter_env="test",
        )
        return settings

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_encryption_service] = override_encryption

    async with AsyncClient(app=app, base_url="http://testserver") as c:
        c.headers["Authorization"] = f"Bearer {raw_key}"
        yield c

    app.dependency_overrides.clear()
