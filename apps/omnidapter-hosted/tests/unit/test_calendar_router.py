"""Unit tests for hosted calendar router helper functions."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from omnidapter_hosted.routers.calendar import _get_conn, _wrap
from omnidapter_server.models.connection import Connection, ConnectionStatus
from starlette.requests import Request


class _ScalarResult:
    def __init__(self, one: object | None) -> None:
        self._one = one

    def scalar_one_or_none(self) -> object | None:
        return self._one


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": []})


@pytest.mark.asyncio
async def test_get_conn_invalid_uuid() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await _get_conn(
            connection_id="invalid",
            tenant_id=uuid.uuid4(),
            session=AsyncMock(),
            request=_request(),
        )

    assert exc_info.value.status_code == 404
    detail = cast(dict[str, Any], exc_info.value.detail)
    assert detail["code"] == "connection_not_found"


@pytest.mark.asyncio
async def test_get_conn_not_found() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(None))

    with pytest.raises(HTTPException) as exc_info:
        await _get_conn(
            connection_id=str(uuid.uuid4()),
            tenant_id=uuid.uuid4(),
            session=session,
            request=_request(),
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_conn_status_guard_returns_error() -> None:
    conn = Connection(
        id=uuid.uuid4(),
        provider_key="google",
        status=ConnectionStatus.NEEDS_REAUTH,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(conn))

    with pytest.raises(HTTPException) as exc_info:
        await _get_conn(
            connection_id=str(conn.id),
            tenant_id=uuid.uuid4(),
            session=session,
            request=_request(),
        )

    assert exc_info.value.status_code == 403


def test_wrap_list_payload_shape() -> None:
    payload = _wrap(data=[{"x": 1}], request_id="req_1")
    assert payload["data"] == [{"x": 1}]
    assert payload["meta"]["request_id"] == "req_1"
