"""Unit tests for calendar router helper functions."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from omnidapter_server.models.connection import Connection, ConnectionStatus
from omnidapter_server.routers.calendar import _get_conn, _wrap
from starlette.requests import Request


class _ScalarResult:
    def __init__(self, one: object | None) -> None:
        self._one = one

    def scalar_one_or_none(self) -> object | None:
        return self._one


class _ModelLike:
    def __init__(self, value: str) -> None:
        self.value = value

    def model_dump(self, mode: str = "json") -> dict[str, str]:
        return {"value": self.value, "mode": mode}


def _request() -> Request:
    req = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    req.state.request_id = "req_1"
    return req


def _connection(status: str = ConnectionStatus.ACTIVE) -> Connection:
    return Connection(
        id=uuid.uuid4(),
        provider_key="google",
        status=status,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def test_wrap_for_list_and_model_like_objects() -> None:
    wrapped = _wrap([_ModelLike("a"), _ModelLike("b")], request_id="req_list")

    assert wrapped["meta"]["request_id"] == "req_list"
    assert wrapped["data"][0]["value"] == "a"


def test_wrap_for_single_model_like_object() -> None:
    wrapped = _wrap(_ModelLike("single"), request_id="req_single")

    assert wrapped["meta"]["request_id"] == "req_single"
    assert wrapped["data"]["value"] == "single"


@pytest.mark.asyncio
async def test_get_conn_invalid_uuid() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await _get_conn("invalid", AsyncMock(), _request())

    assert exc_info.value.status_code == 404
    detail = cast(dict[str, Any], exc_info.value.detail)
    assert detail["code"] == "connection_not_found"


@pytest.mark.asyncio
async def test_get_conn_not_found() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(None))

    with pytest.raises(HTTPException) as exc_info:
        await _get_conn(str(uuid.uuid4()), session, _request())

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_conn_preserves_specific_connection_status_error() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(_connection(ConnectionStatus.REVOKED)))
    error = JSONResponse(
        status_code=410,
        content={"error": {"code": "connection_revoked", "message": "revoked"}},
    )

    with (
        patch("omnidapter_server.routers.calendar.check_connection_status", return_value=error),
        pytest.raises(HTTPException) as exc_info,
    ):
        await _get_conn(str(uuid.uuid4()), session, _request())

    assert exc_info.value.status_code == 410
    detail = cast(dict[str, Any], exc_info.value.detail)
    assert detail["code"] == "connection_revoked"


@pytest.mark.asyncio
async def test_get_conn_success() -> None:
    conn = _connection(ConnectionStatus.ACTIVE)
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(conn))

    with patch("omnidapter_server.routers.calendar.check_connection_status", return_value=None):
        resolved = await _get_conn(str(conn.id), session, _request())

    assert resolved is conn
