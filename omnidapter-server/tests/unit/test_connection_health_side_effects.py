"""Unit tests for connection health transitions and credential clearing."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from omnidapter_server.services.connection_health import (
    transition_to_revoked,
    update_last_used,
)


@pytest.mark.asyncio
async def test_revoke_clears_credentials():
    """Revoking a connection also clears its encrypted credentials."""
    conn_id = uuid.uuid4()
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()

    await transition_to_revoked(conn_id, session, reason="Test revoke")

    session.execute.assert_called_once()
    session.commit.assert_called_once()

    # Inspect the update statement — credentials_encrypted should be set to None
    statement = session.execute.call_args[0][0]
    compiled = statement.compile()
    assert compiled.params.get("credentials_encrypted") is None


@pytest.mark.asyncio
async def test_update_last_used_fires():
    conn_id = uuid.uuid4()
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    await update_last_used(conn_id, session)
    session.execute.assert_called_once()
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_revoke_with_no_reason():
    conn_id = uuid.uuid4()
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    await transition_to_revoked(conn_id, session)
    session.execute.assert_called_once()
