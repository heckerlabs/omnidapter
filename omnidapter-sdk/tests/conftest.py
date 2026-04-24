"""Session-scoped fixtures: Postgres testcontainer + live uvicorn server + SDK client."""

from __future__ import annotations

import asyncio
import os
import socket
import threading
import time
from collections.abc import Generator

# Must be set before omnidapter_server is imported, because main.py creates a
# module-level app = create_app() that calls get_settings() at import time.
os.environ.setdefault("OMNIDAPTER_ENV", "LOCAL")
os.environ.setdefault("OMNIDAPTER_ENCRYPTION_KEY", "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
# Provide a placeholder DB URL so get_settings() doesn't fail on import.
os.environ.setdefault("OMNIDAPTER_DATABASE_URL", "postgresql+asyncpg://placeholder/placeholder")

import pytest
import uvicorn
from omnidapter_server.config import Settings
from omnidapter_server.database import Base

# Import create_app first so that all models register with Base.metadata.
from omnidapter_server.main import create_app
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer

TEST_API_KEY = "omni_sdk_test_key_0123456789ab"
TEST_ENCRYPTION_KEY = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _create_tables(db_url: str) -> None:
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


@pytest.fixture(scope="session")
def server_url() -> Generator[str, None, None]:
    with PostgresContainer("postgres:16-alpine") as pg:
        db_url = pg.get_connection_url().replace("psycopg2", "asyncpg")

        # Set env vars so that database.py's get_settings()-based engine uses the right URL.
        os.environ["OMNIDAPTER_DATABASE_URL"] = db_url
        os.environ["OMNIDAPTER_API_KEY"] = TEST_API_KEY
        os.environ["OMNIDAPTER_ENCRYPTION_KEY"] = TEST_ENCRYPTION_KEY

        # Reset all global singletons so they pick up the new DB URL from env vars.
        import omnidapter_server.config as _config_module
        import omnidapter_server.database as _db_module

        _config_module._settings = None
        _db_module._engine = None
        _db_module._session_factory = None

        # Create all tables now that models are registered (create_app import above
        # triggers model imports which register tables with Base.metadata).
        asyncio.run(_create_tables(db_url))

        settings = Settings(
            omnidapter_database_url=db_url,
            omnidapter_encryption_key=TEST_ENCRYPTION_KEY,
            omnidapter_env="LOCAL",
            omnidapter_api_key=TEST_API_KEY,
        )
        app = create_app(settings=settings)

        port = _free_port()
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()

        # Wait for the server to accept connections (up to 5s).
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                import urllib.request

                urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1)
                break
            except Exception:
                time.sleep(0.05)
        else:
            raise RuntimeError("Server did not start within 5 seconds")

        yield f"http://127.0.0.1:{port}"

        server.should_exit = True
        thread.join(timeout=5)


@pytest.fixture(scope="session")
def sdk_client(server_url: str):
    try:
        from omnidapter_sdk.client import OmnidapterClient
    except ImportError:
        pytest.skip("SDK not generated — run scripts/generate_sdks.sh first")
    return OmnidapterClient(base_url=server_url, api_key=TEST_API_KEY)
