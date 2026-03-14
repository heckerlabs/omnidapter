# Testing

The test suite is split into **unit tests** (no database or network required)
and **integration tests** (require a live PostgreSQL database).

---

## Running Unit Tests

Unit tests run without any external dependencies:

```bash
# From repository root
uv run pytest apps/omnidapter-api/tests/unit/ -v
```

Or run the full workspace test suite:

```bash
uv run pytest
```

Expected output:

```
apps/omnidapter-api/tests/unit/test_auth_middleware.py   10 passed
apps/omnidapter-api/tests/unit/test_connection_state_machine.py  10 passed
apps/omnidapter-api/tests/unit/test_encryption.py        11 passed
apps/omnidapter-api/tests/unit/test_error_mapping.py      9 passed
apps/omnidapter-api/tests/unit/test_pagination.py         7 passed
apps/omnidapter-api/tests/unit/test_rate_limiting.py      6 passed
apps/omnidapter-api/tests/unit/test_usage_metering.py     5 passed

58 passed
```

---

## Unit Test Coverage

| Test file | What it covers |
|---|---|
| `test_encryption.py` | AES-256-GCM roundtrip, unique nonces, wrong key rejection, key rotation, Unicode, empty key error |
| `test_auth_middleware.py` | API key generation format, prefix, bcrypt verification, wrong key rejection |
| `test_connection_state_machine.py` | `record_refresh_failure`, `record_refresh_success`, `transition_to_active`, `transition_to_revoked`, threshold behavior |
| `test_error_mapping.py` | Library exception → HTTP status mapping for all 8 exception types |
| `test_usage_metering.py` | Billable endpoint detection, free tier check logic, `record_usage` write |
| `test_rate_limiting.py` | Sliding window enforcement, org isolation, limits by plan, header generation |
| `test_pagination.py` | `offset`/`limit` calculation, `has_more` flag, boundary cases |

---

## Running Integration Tests

Integration tests require a live PostgreSQL database.

### Set environment variables

```bash
export OMNIDAPTER_INTEGRATION=1
export OMNIDAPTER_TEST_DATABASE_URL=postgresql+asyncpg://localhost/omnidapter_test
export OMNIDAPTER_ENCRYPTION_KEY=<base64-32-byte-key>
```

### Run

```bash
uv run pytest apps/omnidapter-api/tests/integration/ -v
```

Or run all tests including integration:

```bash
OMNIDAPTER_INTEGRATION=1 \
OMNIDAPTER_TEST_DATABASE_URL=postgresql+asyncpg://localhost/omnidapter_test \
uv run pytest
```

---

## Integration Test Coverage

| Test file | What it tests |
|---|---|
| `test_api_key_lifecycle.py` | Create org + key, authenticate, revoke key |
| `test_connection_crud.py` | Create, list (filtered/paginated), get, delete connections |
| `test_connection_health.py` | Refresh failure counting, threshold transition, success reset |
| `test_provider_config.py` | Upsert, get, list, delete provider configs; encryption round-trip |
| `test_oauth_flow.py` | Full OAuth begin → callback → active flow (mocked provider token exchange) |
| `test_calendar_proxy.py` | All calendar endpoints with mocked omnidapter library calls |
| `test_usage_recording.py` | Usage records written per call; free tier enforcement; `GET /v1/usage` |
| `test_org_isolation.py` | Org A cannot access Org B's connections, configs, or usage data |

---

## Test Infrastructure

### Fixtures (`tests/integration/conftest.py`)

| Fixture | Scope | Description |
|---|---|---|
| `setup_database` | session | Creates all tables via `Base.metadata.create_all`; drops at end |
| `session` | function | Per-test DB session with transactional rollback |
| `org` | function | Creates a test `Organization` row |
| `api_key` | function | Creates an `APIKey` for the test org; returns `(raw_key, api_key_model)` |
| `client` | function | `httpx.AsyncClient` pointed at the FastAPI app with overridden deps |

### Dependency overrides

The integration test `conftest.py` overrides FastAPI dependencies to use the
test database session and test settings:

```python
app.dependency_overrides[get_session] = lambda: test_session
app.dependency_overrides[get_settings] = lambda: test_settings
app.dependency_overrides[get_encryption_service] = lambda: test_encryption_service
```

### Skipping without Postgres

When `OMNIDAPTER_INTEGRATION=1` is not set, all integration tests are
automatically skipped with:

```
SKIPPED [45] integration tests require OMNIDAPTER_INTEGRATION=1
```

---

## Test Configuration

pytest is configured in the root `pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = [
    "packages/omnidapter/tests",
    "apps/omnidapter-api/tests",
]
```

All async test functions are auto-detected by `pytest-asyncio` in `auto` mode.

---

## Writing New Tests

### Unit test pattern

```python
import pytest
from omnidapter_api.services.rate_limit import check_rate_limit, reset_org_state

def test_rate_limit_free_plan_allows_up_to_limit():
    org_id = "test-org-unit"
    reset_org_state(org_id)

    for _ in range(60):
        allowed, _, _, _ = check_rate_limit(org_id, "free", 60, 300)
        assert allowed

    allowed, _, remaining, _ = check_rate_limit(org_id, "free", 60, 300)
    assert not allowed
    assert remaining == 0
```

### Integration test pattern

```python
import pytest

@pytest.mark.asyncio
async def test_list_connections_empty(client, api_key):
    raw_key, _ = api_key
    resp = await client.get(
        "/v1/connections",
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"] == []
    assert resp.json()["meta"]["pagination"]["total"] == 0
```
