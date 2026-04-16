# SDK Integration Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pytest integration test suite for `omnidapter-sdk` that spins up a real `omnidapter-server` against a Postgres testcontainer and exercises the SDK's request/response serialization for every non-OAuth endpoint.

**Architecture:** A session-scoped pytest fixture starts a `PostgresContainer`, creates the DB schema via `Base.metadata.create_all`, then launches `uvicorn` in a background thread with the test DB URL and a known API key (seeded by the server's own lifespan logic). Tests receive a fully configured `OmnidapterClient` and run synchronously (the SDK uses urllib3, no asyncio needed). All endpoints return `object` (raw dict) because the OpenAPI spec has empty `{}` response schemas — tests assert on the dict structure directly. Calendar tests are limited to verifying 404 responses against a fake connection ID — real calendar data requires a completed OAuth flow which is out of scope.

**Tech Stack:** pytest, testcontainers-python (postgres), uvicorn, omnidapter-server (workspace package), omnidapter-sdk (workspace package)

---

## File Structure

| File | Purpose |
|---|---|
| `omnidapter-sdk/tests/__init__.py` | Empty — makes tests a package |
| `omnidapter-sdk/tests/conftest.py` | Session-scoped Postgres container + uvicorn server + `OmnidapterClient` |
| `omnidapter-sdk/tests/test_providers.py` | `list_providers`, `get_provider`, unknown provider 404 |
| `omnidapter-sdk/tests/test_connections.py` | `list_connections` (empty), `get_connection` 404, `create_connection` unknown provider, `delete_connection` 404 |
| `omnidapter-sdk/tests/test_link_tokens.py` | `create_link_token` with and without options, validation errors |
| `omnidapter-sdk/tests/test_calendar.py` | 404 smoke tests for every calendar route |
| `omnidapter-sdk/pyproject.toml` | Add `[project.optional-dependencies] test = [...]` and `[tool.pytest.ini_options]` |
| `.github/workflows/_test-sdk.yml` | New reusable CI workflow for SDK integration tests |
| `.github/workflows/release.yml` | Add `test-sdk` job wired to `_test-sdk.yml` |

---

## Context you need

**How the server seeds an API key:** `create_app()` has a lifespan hook that calls `_sync_managed_api_key`. If `omnidapter_api_key` is set in the `Settings` object passed to `create_app()`, it upserts that key into the DB on startup. We use this to inject a known key without touching the DB ourselves.

**Auth mode:** Default (`required`). The `OmnidapterClient` sends `Authorization: Bearer {api_key}` on every request — this tests the real auth path.

**Provider registry:** Providers are only registered if their OAuth client ID is configured. With default empty settings used in tests, `list_providers` returns an empty list. We assert on the response envelope shape, not specific providers.

**Connection CRUD without OAuth:** `POST /v1/connections` starts an OAuth flow. If the provider key isn't registered, the server returns 404. We test that the SDK raises `ApiException` with the right status.

**Return types:** All endpoints have `"schema": {}` in the OpenAPI spec, so OAG generates return type `object`. Calling e.g. `sdk_client.providers.list_providers()` returns the raw dict `{"data": [...], "meta": {...}}` directly. No `_return_http_data_only` flag needed.

**Error handling:** OAG raises `omnidapter_sdk.exceptions.ApiException` for non-2xx responses. `exc.status` is the HTTP status code. `exc.body` is the raw response body string.

**OmnidapterClient signature:**
```python
# omnidapter-sdk/omnidapter_sdk/client.py
class OmnidapterClient:
    def __init__(self, base_url: str, api_key: str) -> None: ...
    calendar: CalendarApi
    connections: ConnectionsApi
    link_tokens: LinkTokensApi
    providers: ProvidersApi
```

**Configuration:** `Settings` is at `omnidapter_server.config.Settings`. Key fields for tests:
- `omnidapter_database_url`: asyncpg URL for Postgres
- `omnidapter_encryption_key`: base64 AES-256 key
- `omnidapter_env`: must be `"LOCAL"` for test containers
- `omnidapter_api_key`: raw key string, seeded into DB on startup

**Table creation:** The server does NOT run Alembic migrations automatically. Tests must call `Base.metadata.create_all` (from `omnidapter_server.database.Base`) before starting uvicorn.

**Existing test workflow:** `.github/workflows/_test-python.yml` calls `poe test` which runs only server tests. SDK tests need their own `_test-sdk.yml`.

**How to run tests locally:**
```bash
uv run pytest omnidapter-sdk/tests/ -v
```

---

## Task 1: Add test dependencies and pytest config

**Files:**
- Modify: `omnidapter-sdk/pyproject.toml`

- [ ] **Step 1: Add optional test deps and pytest config to `omnidapter-sdk/pyproject.toml`**

```toml
[project]
name = "omnidapter-sdk"
version = "0.0.0"
description = "Omnidapter API client SDK"
license = { text = "MIT" }
requires-python = ">=3.10"
dependencies = [
    "urllib3>=1.25.3",
    "python-dateutil>=2.8.2",
    "pydantic>=1.9.2",
]

[project.optional-dependencies]
test = [
    "pytest>=8.0",
    "testcontainers[postgres]>=4.0",
    "uvicorn>=0.30",
    "omnidapter-server",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["omnidapter_sdk"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Sync the workspace**

```bash
uv sync
```

Expected: no errors, lockfile updated.

- [ ] **Step 3: Commit**

```bash
git add omnidapter-sdk/pyproject.toml uv.lock
git commit -m "chore: add test dependencies to omnidapter-sdk"
```

---

## Task 2: Write the test conftest

**Files:**
- Create: `omnidapter-sdk/tests/__init__.py`
- Create: `omnidapter-sdk/tests/conftest.py`

- [ ] **Step 1: Create the empty `__init__.py`**

```bash
touch omnidapter-sdk/tests/__init__.py
```

- [ ] **Step 2: Write `omnidapter-sdk/tests/conftest.py`**

```python
"""Session-scoped fixtures: Postgres testcontainer + live uvicorn server + SDK client."""

from __future__ import annotations

import asyncio
import socket
import threading
import time
from collections.abc import Generator

import pytest
import uvicorn
from omnidapter_server.config import Settings
from omnidapter_server.database import Base
from omnidapter_server.main import create_app
from omnidapter_sdk.client import OmnidapterClient
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
def sdk_client(server_url: str) -> OmnidapterClient:
    return OmnidapterClient(base_url=server_url, api_key=TEST_API_KEY)
```

- [ ] **Step 3: Verify the fixtures load without error (no test files yet)**

```bash
uv run pytest omnidapter-sdk/tests/ --collect-only 2>&1 | head -20
```

Expected: `0 tests collected` with no import errors.

- [ ] **Step 4: Commit**

```bash
git add omnidapter-sdk/tests/__init__.py omnidapter-sdk/tests/conftest.py
git commit -m "test: add SDK integration test conftest with Postgres testcontainer"
```

---

## Task 3: Provider tests

**Files:**
- Create: `omnidapter-sdk/tests/test_providers.py`

- [ ] **Step 1: Write `omnidapter-sdk/tests/test_providers.py`**

```python
"""Integration tests for ProvidersApi."""

import pytest
from omnidapter_sdk.client import OmnidapterClient
from omnidapter_sdk.exceptions import ApiException


def test_list_providers_returns_envelope(sdk_client: OmnidapterClient):
    body = sdk_client.providers.list_providers()
    assert "data" in body
    assert "meta" in body
    assert isinstance(body["data"], list)


def test_get_unknown_provider_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.providers.get_provider("nonexistent_provider_xyz")
    assert exc_info.value.status == 404
```

- [ ] **Step 2: Run the tests**

```bash
uv run pytest omnidapter-sdk/tests/test_providers.py -v
```

Expected:
```
PASSED tests/test_providers.py::test_list_providers_returns_envelope
PASSED tests/test_providers.py::test_get_unknown_provider_raises_404
```

- [ ] **Step 3: Commit**

```bash
git add omnidapter-sdk/tests/test_providers.py
git commit -m "test: add SDK integration tests for providers endpoints"
```

---

## Task 4: Connection tests

**Files:**
- Create: `omnidapter-sdk/tests/test_connections.py`

No OAuth providers are configured in test settings, so `create_connection` always returns 404 (provider not found). `list_connections` returns an empty list. We test `get_connection` and `delete_connection` with a nil UUID to verify 404 handling.

- [ ] **Step 1: Write `omnidapter-sdk/tests/test_connections.py`**

```python
"""Integration tests for ConnectionsApi."""

import pytest
from omnidapter_sdk.client import OmnidapterClient
from omnidapter_sdk.exceptions import ApiException
from omnidapter_sdk.models import CreateConnectionRequest

NIL_UUID = "00000000-0000-0000-0000-000000000000"


def test_list_connections_empty(sdk_client: OmnidapterClient):
    body = sdk_client.connections.list_connections()
    assert "data" in body
    assert body["data"] == []
    assert body["meta"]["pagination"]["total"] == 0


def test_list_connections_with_filters(sdk_client: OmnidapterClient):
    body = sdk_client.connections.list_connections(provider="google", status="active")
    assert body["data"] == []


def test_get_connection_unknown_id_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.connections.get_connection(NIL_UUID)
    assert exc_info.value.status == 404


def test_create_connection_unknown_provider_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.connections.create_connection(
            CreateConnectionRequest(provider_key="nonexistent_provider_xyz")
        )
    assert exc_info.value.status == 404


def test_delete_connection_unknown_id_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.connections.delete_connection(NIL_UUID)
    assert exc_info.value.status == 404
```

- [ ] **Step 2: Run the tests**

```bash
uv run pytest omnidapter-sdk/tests/test_connections.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add omnidapter-sdk/tests/test_connections.py
git commit -m "test: add SDK integration tests for connections endpoints"
```

---

## Task 5: Link token tests

**Files:**
- Create: `omnidapter-sdk/tests/test_link_tokens.py`

- [ ] **Step 1: Write `omnidapter-sdk/tests/test_link_tokens.py`**

```python
"""Integration tests for LinkTokensApi."""

import pytest
from omnidapter_sdk.client import OmnidapterClient
from omnidapter_sdk.exceptions import ApiException
from omnidapter_sdk.models import CreateLinkTokenRequest

NIL_UUID = "00000000-0000-0000-0000-000000000000"


def test_create_link_token_minimal(sdk_client: OmnidapterClient):
    body = sdk_client.link_tokens.create_link_token(CreateLinkTokenRequest())
    assert "data" in body
    token_data = body["data"]
    assert token_data["token"].startswith("lt_")
    assert "expires_at" in token_data
    assert "connect_url" in token_data


def test_create_link_token_with_options(sdk_client: OmnidapterClient):
    body = sdk_client.link_tokens.create_link_token(
        CreateLinkTokenRequest(
            end_user_id="user_123",
            allowed_providers=["google"],
            ttl_seconds=300,
        )
    )
    assert body["data"]["token"].startswith("lt_")


def test_create_link_token_with_unknown_connection_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.link_tokens.create_link_token(
            CreateLinkTokenRequest(connection_id=NIL_UUID)
        )
    assert exc_info.value.status == 404


def test_create_link_token_ttl_too_short_raises_422(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.link_tokens.create_link_token(
            CreateLinkTokenRequest(ttl_seconds=10)
        )
    assert exc_info.value.status == 422
```

- [ ] **Step 2: Run the tests**

```bash
uv run pytest omnidapter-sdk/tests/test_link_tokens.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add omnidapter-sdk/tests/test_link_tokens.py
git commit -m "test: add SDK integration tests for link tokens endpoint"
```

---

## Task 6: Calendar smoke tests

**Files:**
- Create: `omnidapter-sdk/tests/test_calendar.py`

Calendar operations require a completed OAuth connection. These tests verify that routes exist, path parameters are serialized correctly, and error responses are parsed — by asserting 404 for a fake connection ID.

- [ ] **Step 1: Write `omnidapter-sdk/tests/test_calendar.py`**

```python
"""Integration smoke tests for CalendarApi — verifies routing and error parsing."""

import pytest
from omnidapter_sdk.client import OmnidapterClient
from omnidapter_sdk.exceptions import ApiException
from omnidapter_sdk.models import CreateCalendarRequest, CreateEventRequest

FAKE_CONNECTION = "00000000-0000-0000-0000-000000000000"
FAKE_CALENDAR = "cal_fake"
FAKE_EVENT = "evt_fake"


def test_list_calendars_unknown_connection_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.calendar.list_calendars(FAKE_CONNECTION)
    assert exc_info.value.status == 404


def test_get_calendar_unknown_connection_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.calendar.get_calendar(FAKE_CONNECTION, FAKE_CALENDAR)
    assert exc_info.value.status == 404


def test_create_calendar_unknown_connection_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.calendar.create_calendar(
            FAKE_CONNECTION,
            CreateCalendarRequest(name="Test Calendar"),
        )
    assert exc_info.value.status == 404


def test_list_events_unknown_connection_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.calendar.list_events(FAKE_CONNECTION, FAKE_CALENDAR)
    assert exc_info.value.status == 404


def test_get_event_unknown_connection_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.calendar.get_event(FAKE_CONNECTION, FAKE_CALENDAR, FAKE_EVENT)
    assert exc_info.value.status == 404


def test_create_event_unknown_connection_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.calendar.create_event(
            FAKE_CONNECTION,
            FAKE_CALENDAR,
            CreateEventRequest(
                title="Test Event",
                start={"date_time": "2026-05-01T10:00:00Z"},
                end={"date_time": "2026-05-01T11:00:00Z"},
            ),
        )
    assert exc_info.value.status == 404
```

- [ ] **Step 2: Run the tests**

```bash
uv run pytest omnidapter-sdk/tests/test_calendar.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add omnidapter-sdk/tests/test_calendar.py
git commit -m "test: add SDK integration smoke tests for calendar endpoints"
```

---

## Task 7: Wire up CI

**Files:**
- Create: `.github/workflows/_test-sdk.yml`
- Modify: `.github/workflows/release.yml`

The existing `_test-python.yml` runs `poe test` (server tests only). SDK tests need a separate workflow because they require Docker for testcontainers and are not part of `poe test`.

- [ ] **Step 1: Create `.github/workflows/_test-sdk.yml`**

```yaml
name: Test SDK

on:
  workflow_call:

jobs:
  test-sdk:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v5

      - name: Run SDK integration tests
        run: uv run pytest omnidapter-sdk/tests/ -v --tb=short
```

- [ ] **Step 2: Add `test-sdk` job to `.github/workflows/release.yml`**

In `release.yml`, add a new job after the existing `test` job:

```yaml
  test-sdk:
    needs: validate
    uses: ./.github/workflows/_test-sdk.yml
```

Then update the `open-pr` job's `needs` to include it:

```yaml
  open-pr:
    needs: [validate, test, test-sdk]
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/_test-sdk.yml .github/workflows/release.yml
git commit -m "ci: add SDK integration test job to release workflow"
```

---

## Task 8: Full test run and push

- [ ] **Step 1: Run the complete SDK test suite**

```bash
uv run pytest omnidapter-sdk/tests/ -v
```

Expected: all 17 tests PASS, server starts once (session scope), Postgres container starts once.

- [ ] **Step 2: Run the full project check to confirm no regressions**

```bash
uv run poe check
```

Expected: passes cleanly.

- [ ] **Step 3: Push**

```bash
git push origin feat/sdk
```
