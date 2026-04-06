"""Unit tests for connections router helper functions."""

from __future__ import annotations

import uuid
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from omnidapter_server.models.connection import Connection, ConnectionStatus
from omnidapter_server.routers.connections import get_connection


class _ScalarResult:
    def __init__(self, one: object | None) -> None:
        self._one = one

    def scalar_one_or_none(self) -> object | None:
        return self._one


@pytest.mark.asyncio
async def test_get_connection_invalid_uuid() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_connection("invalid", AsyncMock())

    assert exc_info.value.status_code == 404
    detail = cast(dict[str, Any], exc_info.value.detail)
    assert detail["code"] == "connection_not_found"


@pytest.mark.asyncio
async def test_get_connection_not_found() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(None))

    with pytest.raises(HTTPException) as exc_info:
        await get_connection(str(uuid.uuid4()), session)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_connection_success() -> None:
    conn = Connection(
        id=uuid.uuid4(),
        provider_key="google",
        status=ConnectionStatus.ACTIVE,
    )
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(conn))

    resolved = await get_connection(str(conn.id), session)

    assert resolved is conn
