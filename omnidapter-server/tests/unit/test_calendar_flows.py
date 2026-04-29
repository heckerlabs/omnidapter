"""Unit tests for shared calendar flows."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from omnidapter_server.models.connection import Connection, ConnectionStatus
from omnidapter_server.services.calendar_flows import (
    execute_calendar_operation,
    get_connection_ready_or_404,
)
from omnidapter_server.services.response_utils import wrap_response
from starlette.requests import Request


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": []})


def _conn(status: str = ConnectionStatus.ACTIVE) -> Connection:
    return Connection(
        id=uuid.uuid4(),
        provider_key="google",
        status=status,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


class _ModelLike:
    def model_dump(self, mode: str = "json") -> dict[str, str]:
        return {"mode": mode}


def test_wrap_response_list_and_model() -> None:
    list_wrapped = wrap_response([_ModelLike()], "req_1")
    obj_wrapped = wrap_response(_ModelLike(), "req_2")
    assert list_wrapped["meta"]["request_id"] == "req_1"
    assert obj_wrapped["meta"]["request_id"] == "req_2"


@pytest.mark.asyncio
async def test_get_connection_ready_or_404_invalid_uuid() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_connection_ready_or_404(
            connection_id="invalid",
            session=AsyncMock(),
            request=_request(),
            load_connection_by_uuid=AsyncMock(),
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_connection_ready_or_404_status_error() -> None:
    conn = _conn(ConnectionStatus.REVOKED)
    check_status = MagicMock(
        return_value=JSONResponse(
            status_code=410,
            content={"error": {"code": "connection_revoked", "message": "revoked"}},
        )
    )
    with pytest.raises(HTTPException) as exc_info:
        await get_connection_ready_or_404(
            connection_id=str(conn.id),
            session=AsyncMock(),
            request=_request(),
            load_connection_by_uuid=AsyncMock(return_value=conn),
            check_status=check_status,
        )
    assert exc_info.value.status_code == 410


@pytest.mark.asyncio
async def test_execute_calendar_operation_success() -> None:
    conn = _conn()
    calendar = SimpleNamespace(list_calendars=AsyncMock(return_value=[{"id": "cal_1"}]))
    lib_conn = SimpleNamespace(calendar=lambda: calendar)
    omni = SimpleNamespace(connection=AsyncMock(return_value=lib_conn))

    result = await execute_calendar_operation(
        connection_id=str(conn.id),
        request=_request(),
        session=AsyncMock(),
        load_connection=AsyncMock(return_value=conn),
        build_omni=AsyncMock(return_value=omni),
        operation=lambda cal: cal.list_calendars(),
        update_last_used=AsyncMock(),
    )

    assert result == [{"id": "cal_1"}]


@pytest.mark.asyncio
async def test_execute_calendar_operation_maps_library_exception() -> None:
    conn = _conn()
    omni = SimpleNamespace(connection=AsyncMock(side_effect=RuntimeError("boom")))
    mapped = JSONResponse(status_code=500, content={"error": {"code": "x", "message": "y"}})

    with patch(
        "omnidapter_server.services.calendar_flows.map_library_exception", return_value=mapped
    ):
        result = await execute_calendar_operation(
            connection_id=str(conn.id),
            request=_request(),
            session=AsyncMock(),
            load_connection=AsyncMock(return_value=conn),
            build_omni=AsyncMock(return_value=omni),
            operation=AsyncMock(),
            update_last_used=AsyncMock(),
        )

    assert result is mapped
