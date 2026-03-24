"""Unit tests for connection state machine logic."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from omnidapter_server.models.connection import ConnectionStatus
from omnidapter_server.services.connection_health import (
    record_refresh_failure,
    record_refresh_success,
    transition_to_active,
    transition_to_revoked,
)


def _make_session(returned_status: str | None) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = returned_status
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_refresh_failure_increments_count():
    session = _make_session(ConnectionStatus.ACTIVE)
    new_status = await record_refresh_failure(uuid.uuid4(), session, reauth_threshold=3)
    assert new_status == ConnectionStatus.ACTIVE
    # execute should have been called (with update)
    session.execute.assert_called()


@pytest.mark.asyncio
async def test_refresh_failure_reaches_threshold():
    session = _make_session(ConnectionStatus.NEEDS_REAUTH)
    new_status = await record_refresh_failure(uuid.uuid4(), session, reauth_threshold=3)
    assert new_status == ConnectionStatus.NEEDS_REAUTH


@pytest.mark.asyncio
async def test_refresh_failure_below_threshold():
    session = _make_session(ConnectionStatus.ACTIVE)
    new_status = await record_refresh_failure(uuid.uuid4(), session, reauth_threshold=3)
    assert new_status == ConnectionStatus.ACTIVE


@pytest.mark.asyncio
async def test_refresh_failure_already_needs_reauth():
    session = _make_session(ConnectionStatus.NEEDS_REAUTH)
    new_status = await record_refresh_failure(uuid.uuid4(), session, reauth_threshold=3)
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
    session = _make_session(None)
    status = await record_refresh_failure(uuid.uuid4(), session, reauth_threshold=3)
    assert status == ConnectionStatus.REVOKED


def test_connection_status_values():
    assert ConnectionStatus.PENDING == "pending"
    assert ConnectionStatus.ACTIVE == "active"
    assert ConnectionStatus.NEEDS_REAUTH == "needs_reauth"
    assert ConnectionStatus.REVOKED == "revoked"
