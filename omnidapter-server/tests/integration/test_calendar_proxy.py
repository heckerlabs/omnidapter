"""Integration tests for calendar service proxy endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from omnidapter_server.models.connection import Connection, ConnectionStatus
from sqlalchemy.ext.asyncio import AsyncSession


def _make_calendar_event(calendar_id: str = "primary", event_id: str = "evt_1") -> MagicMock:
    from omnidapter import CalendarEvent, EventStatus

    event = MagicMock(spec=CalendarEvent)
    event.event_id = event_id
    event.calendar_id = calendar_id
    event.summary = "Test Event"
    event.start = datetime(2026, 3, 14, 10, 0, tzinfo=timezone.utc)
    event.end = datetime(2026, 3, 14, 11, 0, tzinfo=timezone.utc)
    event.status = EventStatus.CONFIRMED
    event.model_dump = lambda **kw: {
        "event_id": event_id,
        "calendar_id": calendar_id,
        "summary": "Test Event",
        "start": "2026-03-14T10:00:00Z",
        "end": "2026-03-14T11:00:00Z",
    }
    return event


def _make_calendar(calendar_id: str = "primary") -> MagicMock:
    from omnidapter import Calendar

    cal = MagicMock(spec=Calendar)
    cal.calendar_id = calendar_id
    cal.summary = "Test Calendar"
    cal.model_dump = lambda **kw: {
        "calendar_id": calendar_id,
        "summary": "Test Calendar",
    }
    return cal


async def _aiter(*items):
    """Helper to make an async iterator from items."""
    for item in items:
        yield item


@pytest_asyncio.fixture
async def active_connection(session: AsyncSession) -> Connection:
    conn = Connection(
        id=uuid.uuid4(),
        provider_key="google",
        external_id="calendar_test_user",
        status=ConnectionStatus.ACTIVE,
        credentials_encrypted="placeholder",  # We'll mock the omni calls
    )
    session.add(conn)
    await session.flush()
    return conn


@pytest.mark.asyncio
async def test_list_calendars(
    client: AsyncClient,
    session: AsyncSession,
    active_connection: Connection,
):
    """GET /calendars calls library and returns normalized response."""
    mock_calendar = _make_calendar()

    with patch("omnidapter_server.routers.calendar.Omnidapter") as MockOmni:
        mock_omni_inst = MagicMock()
        mock_conn = MagicMock()
        mock_cal_svc = MagicMock()
        mock_cal_svc.list_calendars = AsyncMock(return_value=[mock_calendar])
        mock_conn.calendar = MagicMock(return_value=mock_cal_svc)
        mock_omni_inst.connection = AsyncMock(return_value=mock_conn)
        MockOmni.return_value = mock_omni_inst

        response = await client.get(f"/v1/connections/{active_connection.id}/calendars")

    assert response.status_code == 200
    data = response.json()["data"]
    assert isinstance(data, list)
    assert len(data) == 1


@pytest.mark.asyncio
async def test_get_calendar(
    client: AsyncClient,
    session: AsyncSession,
    active_connection: Connection,
):
    """GET /calendars/{calendar_id} returns a calendar."""
    mock_calendar = _make_calendar()

    with patch("omnidapter_server.routers.calendar.Omnidapter") as MockOmni:
        mock_omni_inst = MagicMock()
        mock_conn = MagicMock()
        mock_cal_svc = MagicMock()
        mock_cal_svc.get_calendar = AsyncMock(return_value=mock_calendar)
        mock_conn.calendar = MagicMock(return_value=mock_cal_svc)
        mock_omni_inst.connection = AsyncMock(return_value=mock_conn)
        MockOmni.return_value = mock_omni_inst

        response = await client.get(f"/v1/connections/{active_connection.id}/calendars/primary")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["calendar_id"] == "primary"


@pytest.mark.asyncio
async def test_create_calendar(
    client: AsyncClient,
    session: AsyncSession,
    active_connection: Connection,
):
    """POST /calendars creates a calendar."""
    mock_calendar = _make_calendar()

    with patch("omnidapter_server.routers.calendar.Omnidapter") as MockOmni:
        mock_omni_inst = MagicMock()
        mock_conn = MagicMock()
        mock_cal_svc = MagicMock()
        mock_cal_svc.create_calendar = AsyncMock(return_value=mock_calendar)
        mock_conn.calendar = MagicMock(return_value=mock_cal_svc)
        mock_omni_inst.connection = AsyncMock(return_value=mock_conn)
        MockOmni.return_value = mock_omni_inst

        response = await client.post(
            f"/v1/connections/{active_connection.id}/calendars",
            json={"summary": "New Calendar"},
        )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["summary"] == "Test Calendar"


@pytest.mark.asyncio
async def test_update_calendar(
    client: AsyncClient,
    session: AsyncSession,
    active_connection: Connection,
):
    """PATCH /calendars/{calendar_id} updates a calendar."""
    mock_calendar = _make_calendar()

    with patch("omnidapter_server.routers.calendar.Omnidapter") as MockOmni:
        mock_omni_inst = MagicMock()
        mock_conn = MagicMock()
        mock_cal_svc = MagicMock()
        mock_cal_svc.update_calendar = AsyncMock(return_value=mock_calendar)
        mock_conn.calendar = MagicMock(return_value=mock_cal_svc)
        mock_omni_inst.connection = AsyncMock(return_value=mock_conn)
        MockOmni.return_value = mock_omni_inst

        response = await client.patch(
            f"/v1/connections/{active_connection.id}/calendars/primary",
            json={"calendar_id": "primary", "summary": "Updated Calendar"},
        )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_delete_calendar(
    client: AsyncClient,
    session: AsyncSession,
    active_connection: Connection,
):
    """DELETE /calendars/{calendar_id} deletes a calendar."""
    with patch("omnidapter_server.routers.calendar.Omnidapter") as MockOmni:
        mock_omni_inst = MagicMock()
        mock_conn = MagicMock()
        mock_cal_svc = MagicMock()
        mock_cal_svc.delete_calendar = AsyncMock()
        mock_conn.calendar = MagicMock(return_value=mock_cal_svc)
        mock_omni_inst.connection = AsyncMock(return_value=mock_conn)
        MockOmni.return_value = mock_omni_inst

        response = await client.delete(f"/v1/connections/{active_connection.id}/calendars/primary")

    assert response.status_code == 204


async def test_list_events(
    client: AsyncClient,
    session: AsyncSession,
    active_connection: Connection,
):
    """GET /calendars/{calendar_id}/events returns events from library."""
    mock_event = _make_calendar_event()

    async def _fake_list_events(**kw):
        yield mock_event

    with patch("omnidapter_server.routers.calendar.Omnidapter") as MockOmni:
        mock_omni_inst = MagicMock()
        mock_conn = MagicMock()
        mock_cal_svc = MagicMock()
        mock_cal_svc.list_events = _fake_list_events
        mock_conn.calendar = MagicMock(return_value=mock_cal_svc)
        mock_omni_inst.connection = AsyncMock(return_value=mock_conn)
        MockOmni.return_value = mock_omni_inst

        response = await client.get(
            f"/v1/connections/{active_connection.id}/calendars/primary/events"
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_list_events_respects_limit(
    client: AsyncClient,
    session: AsyncSession,
    active_connection: Connection,
):
    """GET /events with limit only returns requested number of events."""
    mock_event = _make_calendar_event()

    async def _fake_list_events(**kw):
        for _ in range(10):
            yield mock_event

    with patch("omnidapter_server.routers.calendar.Omnidapter") as MockOmni:
        mock_omni_inst = MagicMock()
        mock_conn = MagicMock()
        mock_cal_svc = MagicMock()
        mock_cal_svc.list_events = _fake_list_events
        mock_conn.calendar = MagicMock(return_value=mock_cal_svc)
        mock_omni_inst.connection = AsyncMock(return_value=mock_conn)
        MockOmni.return_value = mock_omni_inst

        response = await client.get(
            f"/v1/connections/{active_connection.id}/calendars/primary/events?limit=3"
        )

    assert response.status_code == 200
    data = response.json()["data"]
    meta = response.json()["meta"]
    assert len(data) == 3
    assert meta["pagination"]["limit"] == 3
    assert meta["pagination"]["offset"] == 0
    assert meta["pagination"]["count"] == 3
    assert meta["pagination"]["has_more"] is True


@pytest.mark.asyncio
async def test_list_events_with_offset(
    client: AsyncClient,
    session: AsyncSession,
    active_connection: Connection,
):
    """GET /events with offset skips events and respects pagination."""
    mock_event = _make_calendar_event()

    async def _fake_list_events(**kw):
        for _ in range(10):
            yield mock_event

    with patch("omnidapter_server.routers.calendar.Omnidapter") as MockOmni:
        mock_omni_inst = MagicMock()
        mock_conn = MagicMock()
        mock_cal_svc = MagicMock()
        mock_cal_svc.list_events = _fake_list_events
        mock_conn.calendar = MagicMock(return_value=mock_cal_svc)
        mock_omni_inst.connection = AsyncMock(return_value=mock_conn)
        MockOmni.return_value = mock_omni_inst

        response = await client.get(
            f"/v1/connections/{active_connection.id}/calendars/primary/events?limit=3&offset=5"
        )

    assert response.status_code == 200
    data = response.json()["data"]
    meta = response.json()["meta"]
    assert len(data) == 3
    assert meta["pagination"]["limit"] == 3
    assert meta["pagination"]["offset"] == 5
    assert meta["pagination"]["count"] == 3
    assert meta["pagination"]["has_more"] is True


@pytest.mark.asyncio
async def test_create_event(
    client: AsyncClient,
    session: AsyncSession,
    active_connection: Connection,
):
    """POST /calendars/{calendar_id}/events creates an event via library."""
    mock_event = _make_calendar_event()

    with patch("omnidapter_server.routers.calendar.Omnidapter") as MockOmni:
        mock_omni_inst = MagicMock()
        mock_conn = MagicMock()
        mock_cal_svc = MagicMock()
        mock_cal_svc.create_event = AsyncMock(return_value=mock_event)
        mock_conn.calendar = MagicMock(return_value=mock_cal_svc)
        mock_omni_inst.connection = AsyncMock(return_value=mock_conn)
        MockOmni.return_value = mock_omni_inst

        response = await client.post(
            f"/v1/connections/{active_connection.id}/calendars/primary/events",
            json={
                "summary": "New Meeting",
                "start": "2026-03-15T14:00:00Z",
                "end": "2026-03-15T15:00:00Z",
            },
        )

    assert response.status_code == 201


@pytest.mark.asyncio
async def test_calendar_returns_error_for_needs_reauth(
    client: AsyncClient,
    session: AsyncSession,
):
    """Calendar endpoint returns 403 for needs_reauth connection."""
    conn = Connection(
        id=uuid.uuid4(),
        provider_key="google",
        external_id="reauth_user",
        status=ConnectionStatus.NEEDS_REAUTH,
    )
    session.add(conn)
    await session.flush()

    response = await client.get(f"/v1/connections/{conn.id}/calendars")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_calendar_returns_error_for_revoked(
    client: AsyncClient,
    session: AsyncSession,
):
    """Calendar endpoint returns 410 for revoked connection."""
    conn = Connection(
        id=uuid.uuid4(),
        provider_key="google",
        external_id="revoked_user",
        status=ConnectionStatus.REVOKED,
    )
    session.add(conn)
    await session.flush()

    response = await client.get(f"/v1/connections/{conn.id}/calendars")
    assert response.status_code == 410


@pytest.mark.asyncio
async def test_last_used_updated_after_calendar_call(
    client: AsyncClient,
    session: AsyncSession,
    active_connection: Connection,
):
    """last_used_at is updated on connection after service call."""
    with patch("omnidapter_server.routers.calendar.Omnidapter") as MockOmni:
        mock_omni_inst = MagicMock()
        mock_conn = MagicMock()
        mock_cal_svc = MagicMock()
        mock_cal_svc.list_calendars = AsyncMock(return_value=[])
        mock_conn.calendar = MagicMock(return_value=mock_cal_svc)
        mock_omni_inst.connection = AsyncMock(return_value=mock_conn)
        MockOmni.return_value = mock_omni_inst

        await client.get(f"/v1/connections/{active_connection.id}/calendars")

    await session.refresh(active_connection)
    assert active_connection.last_used_at is not None
