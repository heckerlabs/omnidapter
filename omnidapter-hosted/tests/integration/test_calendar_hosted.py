"""Integration tests for Hosted Calendar Proxy."""

from __future__ import annotations

import unittest.mock
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from omnidapter_hosted.models.tenant import Tenant
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def api_key_client(db_session: AsyncSession, test_tenant: Tenant) -> AsyncClient:
    """An AsyncClient authenticated with a valid Hosted API Key (omni_*)."""
    from omnidapter_hosted.config import HostedSettings
    from omnidapter_hosted.main import create_app
    from omnidapter_hosted.models.api_key import HostedAPIKey
    from omnidapter_server.database import get_session

    api_key = HostedAPIKey(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        name="test-key",
        key_hash="hash",
        key_prefix="omni_test",
    )
    db_session.add(api_key)
    await db_session.flush()

    settings = HostedSettings()
    settings.jwt_secret = "a" * 32
    app = create_app(settings=settings)

    async def _get_session_override():
        yield db_session

    app.dependency_overrides[get_session] = _get_session_override

    # We use a mocked authenticate_hosted_key to avoid re-hashing logic
    with unittest.mock.patch(
        "omnidapter_hosted.dependencies.authenticate_hosted_key",
        AsyncMock(return_value=(api_key, test_tenant)),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Authorization": "Bearer omni_test_valid"},
        ) as ac:
            yield ac


@unittest.mock.patch("omnidapter_hosted.routers.calendar.execute_calendar_operation")
async def test_list_calendars_proxy(mock_execute, api_key_client: AsyncClient):
    """Test GET /v1/connections/{id}/calendars through the proxy."""
    # Mock successful calendar list
    mock_execute.return_value = [{"id": "cal_1", "name": "Primary"}]

    conn_id = str(uuid.uuid4())
    response = await api_key_client.get(f"/v1/connections/{conn_id}/calendars")

    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["id"] == "cal_1"


@unittest.mock.patch("omnidapter_hosted.routers.calendar.execute_calendar_operation")
async def test_list_events_proxy(mock_execute, api_key_client: AsyncClient):
    """Test GET /v1/connections/{id}/calendars/{id}/events through the proxy."""
    # Mock successful event list
    mock_execute.return_value = [{"id": "evt_1", "summary": "Meeting"}]

    conn_id = str(uuid.uuid4())
    cal_id = "primary"
    response = await api_key_client.get(f"/v1/connections/{conn_id}/calendars/{cal_id}/events")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data[0]["summary"] == "Meeting"


@unittest.mock.patch("omnidapter_hosted.routers.calendar.execute_calendar_operation")
async def test_create_event_proxy(mock_execute, api_key_client: AsyncClient):
    """Test POST /v1/connections/{id}/calendars/{id}/events through the proxy."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result
    # Mock successful event creation
    mock_execute.return_value = {"id": "evt_new", "summary": "New Meeting"}

    conn_id = str(uuid.uuid4())
    cal_id = "primary"
    payload = {
        "summary": "New Meeting",
        "start": "2026-04-01T10:00:00Z",
        "end": "2026-04-01T11:00:00Z",
    }
    response = await api_key_client.post(
        f"/v1/connections/{conn_id}/calendars/{cal_id}/events", json=payload
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["id"] == "evt_new"


@unittest.mock.patch("omnidapter_hosted.routers.calendar.execute_calendar_operation")
async def test_get_availability_proxy(mock_execute, api_key_client: AsyncClient):
    """Test GET /v1/connections/{id}/calendars/{id}/availability through the proxy."""
    mock_execute.return_value = {"busy": []}

    conn_id = str(uuid.uuid4())
    cal_id = "primary"
    response = await api_key_client.get(
        f"/v1/connections/{conn_id}/calendars/{cal_id}/availability",
        params={"start": "2026-04-01T00:00:00Z", "end": "2026-04-02T00:00:00Z"},
    )

    assert response.status_code == 200
    assert "busy" in response.json()["data"]
