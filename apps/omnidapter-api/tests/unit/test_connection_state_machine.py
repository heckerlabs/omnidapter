"""Unit tests for connection state machine logic."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from omnidapter_api.models.connection import Connection, ConnectionStatus
from omnidapter_api.services.connection_health import (
    record_refresh_failure,
    record_refresh_success,
    transition_to_active,
    transition_to_revoked,
)


def _make_conn(status: str = ConnectionStatus.ACTIVE, failures: int = 0) -> Connection:
    conn = MagicMock(spec=Connection)
    conn.id = uuid.uuid4()
    conn.status = status
    conn.refresh_failure_count = failures
    conn.status_reason = None
    return conn


def _make_session(conn: Connection) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()  # Non-async result object
    result.scalar_one_or_none.return_value = conn
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_refresh_failure_increments_count():
    conn = _make_conn(status=ConnectionStatus.ACTIVE, failures=0)
    session = _make_session(conn)
    new_status = await record_refresh_failure(conn.id, session, reauth_threshold=3)
    assert new_status == ConnectionStatus.ACTIVE
    # execute should have been called (with update)
    session.execute.assert_called()


@pytest.mark.asyncio
async def test_refresh_failure_reaches_threshold():
    conn = _make_conn(status=ConnectionStatus.ACTIVE, failures=2)
    session = _make_session(conn)
    new_status = await record_refresh_failure(conn.id, session, reauth_threshold=3)
    assert new_status == ConnectionStatus.NEEDS_REAUTH


@pytest.mark.asyncio
async def test_refresh_failure_below_threshold():
    conn = _make_conn(status=ConnectionStatus.ACTIVE, failures=1)
    session = _make_session(conn)
    new_status = await record_refresh_failure(conn.id, session, reauth_threshold=3)
    assert new_status == ConnectionStatus.ACTIVE


@pytest.mark.asyncio
async def test_refresh_failure_already_needs_reauth():
    conn = _make_conn(status=ConnectionStatus.NEEDS_REAUTH, failures=5)
    session = _make_session(conn)
    new_status = await record_refresh_failure(conn.id, session, reauth_threshold=3)
    # Already in needs_reauth, stays there
    assert new_status == ConnectionStatus.NEEDS_REAUTH


@pytest.mark.asyncio
async def test_refresh_success_resets_count():
    conn_id = uuid.uuid4()
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    await record_refresh_success(conn_id, session)
    session.execute.assert_called_once()
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_transition_to_active():
    conn_id = uuid.uuid4()
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    await transition_to_active(
        conn_id,
        session,
        granted_scopes=["https://www.googleapis.com/auth/calendar"],
        provider_account_id="user@gmail.com",
    )
    session.execute.assert_called_once()
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_transition_to_revoked():
    conn_id = uuid.uuid4()
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    await transition_to_revoked(conn_id, session, reason="Deleted by org")
    session.execute.assert_called_once()
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_refresh_failure_not_found():
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()
    status = await record_refresh_failure(uuid.uuid4(), session, reauth_threshold=3)
    assert status == ConnectionStatus.REVOKED


def test_connection_status_values():
    assert ConnectionStatus.PENDING == "pending"
    assert ConnectionStatus.ACTIVE == "active"
    assert ConnectionStatus.NEEDS_REAUTH == "needs_reauth"
    assert ConnectionStatus.REVOKED == "revoked"
