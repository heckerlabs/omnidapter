"""Integration tests for connection last_used_at updates."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from omnidapter_server.models.connection import Connection, ConnectionStatus
from omnidapter_server.services.connection_health import update_last_used
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_update_last_used_sets_timestamp(session: AsyncSession):
    """update_last_used sets last_used_at on the connection."""
    conn = Connection(
        id=uuid.uuid4(),
        provider_key="google",
        external_id="last_used_test",
        status=ConnectionStatus.ACTIVE,
    )
    session.add(conn)
    await session.flush()

    assert conn.last_used_at is None

    before = datetime.now(timezone.utc)
    await update_last_used(conn.id, session)
    await session.refresh(conn)

    assert conn.last_used_at is not None
    assert conn.last_used_at >= before


@pytest.mark.asyncio
async def test_update_last_used_advances_timestamp(session: AsyncSession):
    """Calling update_last_used twice advances the timestamp."""
    conn = Connection(
        id=uuid.uuid4(),
        provider_key="google",
        external_id="last_used_advance",
        status=ConnectionStatus.ACTIVE,
    )
    session.add(conn)
    await session.flush()

    await update_last_used(conn.id, session)
    await session.refresh(conn)
    first_ts = conn.last_used_at
    assert first_ts is not None

    # Small delay to ensure clock advances
    import asyncio

    await asyncio.sleep(0.01)

    await update_last_used(conn.id, session)
    await session.refresh(conn)
    second_ts = conn.last_used_at

    assert second_ts is not None
    assert second_ts >= first_ts


@pytest.mark.asyncio
async def test_last_used_updated_after_calendar_call(
    client: AsyncClient,
    session: AsyncSession,
):
    """last_used_at is updated on connection after a calendar service call."""
    conn = Connection(
        id=uuid.uuid4(),
        provider_key="google",
        external_id="calendar_last_used",
        status=ConnectionStatus.ACTIVE,
        credentials_encrypted="placeholder",
    )
    session.add(conn)
    await session.flush()

    assert conn.last_used_at is None

    with patch("omnidapter_server.routers.calendar.Omnidapter") as MockOmni:
        mock_omni_inst = MagicMock()
        mock_conn = MagicMock()
        mock_cal_svc = MagicMock()
        mock_cal_svc.list_calendars = AsyncMock(return_value=[])
        mock_conn.calendar = MagicMock(return_value=mock_cal_svc)
        mock_omni_inst.connection = AsyncMock(return_value=mock_conn)
        MockOmni.return_value = mock_omni_inst

        response = await client.get(f"/v1/connections/{conn.id}/calendars")

    assert response.status_code == 200

    await session.refresh(conn)
    assert conn.last_used_at is not None


@pytest.mark.asyncio
async def test_last_used_updated_after_list_events_call(
    client: AsyncClient,
    session: AsyncSession,
):
    """last_used_at is updated after listing calendar events."""
    conn = Connection(
        id=uuid.uuid4(),
        provider_key="google",
        external_id="events_last_used",
        status=ConnectionStatus.ACTIVE,
        credentials_encrypted="placeholder",
    )
    session.add(conn)
    await session.flush()

    async def _fake_list_events(**kw):
        return
        yield  # make it an async generator

    with patch("omnidapter_server.routers.calendar.Omnidapter") as MockOmni:
        mock_omni_inst = MagicMock()
        mock_conn = MagicMock()
        mock_cal_svc = MagicMock()
        mock_cal_svc.list_events = _fake_list_events
        mock_conn.calendar = MagicMock(return_value=mock_cal_svc)
        mock_omni_inst.connection = AsyncMock(return_value=mock_conn)
        MockOmni.return_value = mock_omni_inst

        response = await client.get(f"/v1/connections/{conn.id}/calendars/primary/events")

    assert response.status_code == 200

    await session.refresh(conn)
    assert conn.last_used_at is not None


@pytest.mark.asyncio
async def test_update_last_used_noop_for_nonexistent_connection(session: AsyncSession):
    """update_last_used does not raise for an unknown connection ID."""
    nonexistent_id = uuid.uuid4()
    # Should not raise
    await update_last_used(nonexistent_id, session)
