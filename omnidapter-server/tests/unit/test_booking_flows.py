"""Unit tests for shared booking flows."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.responses import JSONResponse
from omnidapter_server.models.connection import Connection, ConnectionStatus
from omnidapter_server.services.booking_flows import execute_booking_operation
from starlette.requests import Request


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": []})


def _conn(status: str = ConnectionStatus.ACTIVE) -> Connection:
    return Connection(
        id=uuid.uuid4(),
        provider_key="acuity",
        status=status,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_execute_booking_operation_success() -> None:
    conn = _conn()
    booking_svc = SimpleNamespace(list_services=AsyncMock(return_value=[{"id": "svc-1"}]))
    lib_conn = SimpleNamespace(booking=lambda: booking_svc)
    omni = SimpleNamespace(connection=AsyncMock(return_value=lib_conn))
    update_last_used = AsyncMock()

    result = await execute_booking_operation(
        connection_id=str(conn.id),
        request=_request(),
        session=AsyncMock(),
        load_connection=AsyncMock(return_value=conn),
        build_omni=AsyncMock(return_value=omni),
        operation=lambda bk: bk.list_services(),
        update_last_used=update_last_used,
    )

    assert result == [{"id": "svc-1"}]
    update_last_used.assert_awaited_once_with(conn.id, update_last_used.call_args[0][1])


@pytest.mark.asyncio
async def test_execute_booking_operation_maps_library_exception() -> None:
    conn = _conn()
    omni = SimpleNamespace(connection=AsyncMock(side_effect=RuntimeError("provider down")))
    mapped = JSONResponse(
        status_code=503, content={"error": {"code": "provider_error", "message": "provider down"}}
    )

    with patch(
        "omnidapter_server.services.booking_flows.map_library_exception", return_value=mapped
    ):
        result = await execute_booking_operation(
            connection_id=str(conn.id),
            request=_request(),
            session=AsyncMock(),
            load_connection=AsyncMock(return_value=conn),
            build_omni=AsyncMock(return_value=omni),
            operation=AsyncMock(),
            update_last_used=AsyncMock(),
        )

    assert result is mapped


@pytest.mark.asyncio
async def test_execute_booking_operation_update_last_used_called() -> None:
    conn = _conn()
    booking_svc = SimpleNamespace(get_booking=AsyncMock(return_value={"id": "appt-1"}))
    lib_conn = SimpleNamespace(booking=lambda: booking_svc)
    omni = SimpleNamespace(connection=AsyncMock(return_value=lib_conn))
    update_last_used = AsyncMock()
    session = AsyncMock()

    await execute_booking_operation(
        connection_id=str(conn.id),
        request=_request(),
        session=session,
        load_connection=AsyncMock(return_value=conn),
        build_omni=AsyncMock(return_value=omni),
        operation=lambda bk: bk.get_booking(),
        update_last_used=update_last_used,
    )

    update_last_used.assert_awaited_once_with(conn.id, session)


@pytest.mark.asyncio
async def test_execute_booking_operation_exception_skips_last_used() -> None:
    conn = _conn()
    omni = SimpleNamespace(connection=AsyncMock(side_effect=ValueError("bad")))
    update_last_used = AsyncMock()
    mapped = JSONResponse(status_code=400, content={"error": {"code": "x", "message": "y"}})

    with patch(
        "omnidapter_server.services.booking_flows.map_library_exception", return_value=mapped
    ):
        await execute_booking_operation(
            connection_id=str(conn.id),
            request=_request(),
            session=AsyncMock(),
            load_connection=AsyncMock(return_value=conn),
            build_omni=AsyncMock(return_value=omni),
            operation=AsyncMock(),
            update_last_used=update_last_used,
        )

    update_last_used.assert_not_awaited()
