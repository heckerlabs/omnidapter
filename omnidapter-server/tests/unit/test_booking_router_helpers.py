"""Unit tests for booking router helper functions."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse, Response
from omnidapter_server.models.connection import Connection, ConnectionStatus
from omnidapter_server.routers.booking import _get_conn, _respond, _wrap
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
        provider_key="acuity",
        status=status,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


# ── _wrap / _respond ──────────────────────────────────────────────────────────


def test_wrap_list_of_models() -> None:
    wrapped = _wrap([_ModelLike("a"), _ModelLike("b")], request_id="req_list")

    assert wrapped["meta"]["request_id"] == "req_list"
    assert wrapped["data"][0]["value"] == "a"
    assert wrapped["data"][1]["value"] == "b"


def test_wrap_single_model() -> None:
    wrapped = _wrap(_ModelLike("solo"), request_id="req_solo")

    assert wrapped["meta"]["request_id"] == "req_solo"
    assert wrapped["data"]["value"] == "solo"


def test_respond_wraps_non_response() -> None:
    result = _respond(_ModelLike("x"), "req_x")
    assert isinstance(result, dict)
    assert result["data"]["value"] == "x"


def test_respond_passes_through_response_object() -> None:
    raw = Response(content=b"ok", status_code=204)
    result = _respond(raw, "req_y")
    assert result is raw


# ── _get_conn ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_conn_invalid_uuid() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await _get_conn("not-a-uuid", AsyncMock(), _request())

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
async def test_get_conn_status_error_preserved() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(_connection(ConnectionStatus.REVOKED)))
    error = JSONResponse(
        status_code=410,
        content={"error": {"code": "connection_revoked", "message": "revoked"}},
    )

    with (
        patch("omnidapter_server.routers.booking.check_connection_status", return_value=error),
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

    with patch("omnidapter_server.routers.booking.check_connection_status", return_value=None):
        resolved = await _get_conn(str(conn.id), session, _request())

    assert resolved is conn
