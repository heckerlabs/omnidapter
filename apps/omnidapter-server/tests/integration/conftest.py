"""Integration test fixtures with real Postgres database.

Integration tests are skipped unless OMNIDAPTER_INTEGRATION=1 is set.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from omnidapter_server.database import Base, get_session
from omnidapter_server.encryption import EncryptionService
from omnidapter_server.main import app
from omnidapter_server.models.api_key import APIKey
from omnidapter_server.services.auth import generate_api_key
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DB_URL = os.environ.get(
    "OMNIDAPTER_TEST_DATABASE_URL",
    "postgresql+asyncpg://localhost/omnidapter_test",
)

_SKIP_INTEGRATION = os.environ.get("OMNIDAPTER_INTEGRATION") != "1"
TEST_ENCRYPTION_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="

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
    """Transactional session isolated per test, including commit paths."""
    engine = get_test_engine()
    async with engine.connect() as conn:
        outer_tx = await conn.begin()
        sess = AsyncSession(bind=conn, expire_on_commit=False)

        await conn.begin_nested()

        @event.listens_for(sess.sync_session, "after_transaction_end")
        def _restart_savepoint(sync_session, transaction) -> None:  # type: ignore[no-untyped-def]
            parent = getattr(transaction, "_parent", None)
            if (
                transaction.nested
                and (parent is None or not parent.nested)
                and conn.sync_connection is not None
            ):
                conn.sync_connection.begin_nested()

        yield sess
        event.remove(sess.sync_session, "after_transaction_end", _restart_savepoint)
        await sess.close()
        await outer_tx.rollback()


@pytest.fixture
def encryption() -> EncryptionService:
    return EncryptionService(current_key=TEST_ENCRYPTION_KEY)


@pytest_asyncio.fixture
async def api_key(session: AsyncSession) -> tuple[str, APIKey]:
    """Create a test API key, returning (raw_key, APIKey)."""
    raw_key, key_hash, key_prefix = generate_api_key()
    key = APIKey(
        id=uuid.uuid4(),
        name="test",
        key_hash=key_hash,
        key_prefix=key_prefix,
        is_active=True,
        is_test=False,
    )
    session.add(key)
    await session.flush()
    return raw_key, key


@pytest_asyncio.fixture
async def client(session: AsyncSession, api_key: tuple[str, APIKey]) -> AsyncIterator[AsyncClient]:
    """HTTP test client with API key auth and injected test session."""
    raw_key, _ = api_key

    async def override_session():
        yield session

    from omnidapter_server.config import Settings, get_settings
    from omnidapter_server.dependencies import get_encryption_service

    def override_encryption():
        return EncryptionService(current_key=TEST_ENCRYPTION_KEY)

    def override_settings():
        return Settings(
            omnidapter_database_url=TEST_DB_URL,
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
