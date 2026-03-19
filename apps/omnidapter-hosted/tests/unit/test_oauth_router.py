"""Unit tests for hosted OAuth router helpers."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from omnidapter_hosted.models.connection_owner import HostedConnectionOwner
from omnidapter_hosted.routers.oauth import _append_query_params, _load_connection_with_owner
from omnidapter_server.models.connection import Connection, ConnectionStatus


class _ScalarResult:
    def __init__(self, one: object | None) -> None:
        self._one = one

    def scalar_one_or_none(self) -> object | None:
        return self._one


@pytest.mark.asyncio
async def test_load_connection_with_owner_missing_connection() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(None))

    conn, owner = await _load_connection_with_owner(
        session=session,
        connection_id=uuid.uuid4(),
    )

    assert conn is None
    assert owner is None


@pytest.mark.asyncio
async def test_load_connection_with_owner_success() -> None:
    conn = Connection(id=uuid.uuid4(), provider_key="google", status=ConnectionStatus.ACTIVE)
    owner = HostedConnectionOwner(id=uuid.uuid4(), tenant_id=uuid.uuid4(), connection_id=conn.id)
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_ScalarResult(conn), _ScalarResult(owner)])

    loaded_conn, loaded_owner = await _load_connection_with_owner(
        session=session,
        connection_id=conn.id,
    )

    assert loaded_conn is conn
    assert loaded_owner is owner


def test_append_query_params_preserves_existing_query() -> None:
    url = _append_query_params("https://example.com/cb?x=1", connection_id="abc")
    assert "x=1" in url
    assert "connection_id=abc" in url
