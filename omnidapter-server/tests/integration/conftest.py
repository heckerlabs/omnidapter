"""Integration test fixtures with real Postgres via Testcontainers."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Generator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from omnidapter_server.config import Settings
from omnidapter_server.database import Base, get_session
from omnidapter_server.encryption import EncryptionService
from omnidapter_server.main import create_app
from omnidapter_server.models.api_key import APIKey
from omnidapter_server.services.auth import generate_api_key
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from testcontainers.postgres import PostgresContainer

TEST_ENCRYPTION_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="


@pytest.fixture(scope="session")
def postgres_url() -> Generator[str, None, None]:
    """Start a Postgres container for the test session."""
    with PostgresContainer("postgres:16-alpine") as postgres:
        yield postgres.get_connection_url().replace("psycopg2", "asyncpg")


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture
async def test_engine(postgres_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(postgres_url, echo=False)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def setup_database(test_engine: AsyncEngine):
    """Create tables once per session."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def session(setup_database, test_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Transactional session isolated per test, including commit paths."""
    async with test_engine.connect() as conn:
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
    )
    session.add(key)
    await session.flush()
    return raw_key, key


@pytest_asyncio.fixture
async def client(
    session: AsyncSession, api_key: tuple[str, APIKey], postgres_url: str
) -> AsyncIterator[AsyncClient]:
    """HTTP test client with API key auth and injected test session."""
    raw_key, _ = api_key

    async def override_session():
        yield session

    test_settings = Settings(
        omnidapter_database_url=postgres_url,
        omnidapter_encryption_key=TEST_ENCRYPTION_KEY,
        omnidapter_env="DEV",
    )

    app = create_app(settings=test_settings)
    app.dependency_overrides[get_session] = override_session

    async with AsyncClient(transport=ASGITransport(app), base_url="http://testserver") as c:
        c.headers["Authorization"] = f"Bearer {raw_key}"
        yield c

    app.dependency_overrides.clear()
