"""Unit tests for shared CRM flows."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.responses import JSONResponse
from omnidapter_server.models.connection import Connection, ConnectionStatus
from omnidapter_server.services.crm_flows import execute_crm_operation
from starlette.requests import Request


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": []})


def _conn(status: str = ConnectionStatus.ACTIVE) -> Connection:
    return Connection(
        id=uuid.uuid4(),
        provider_key="hubspot",
        status=status,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_execute_crm_operation_success() -> None:
    conn = _conn()
    crm_svc = SimpleNamespace(list_contacts=AsyncMock(return_value=[{"id": "contact-1"}]))
    lib_conn = SimpleNamespace(crm=lambda: crm_svc)
    omni = SimpleNamespace(connection=AsyncMock(return_value=lib_conn))
    update_last_used = AsyncMock()
    session = AsyncMock()

    result = await execute_crm_operation(
        connection_id=str(conn.id),
        request=_request(),
        session=session,
        load_connection=AsyncMock(return_value=conn),
        build_omni=AsyncMock(return_value=omni),
        operation=lambda crm: crm.list_contacts(),
        update_last_used=update_last_used,
    )

    assert result == [{"id": "contact-1"}]
    update_last_used.assert_awaited_once_with(conn.id, session)


@pytest.mark.asyncio
async def test_execute_crm_operation_maps_library_exception() -> None:
    conn = _conn()
    omni = SimpleNamespace(connection=AsyncMock(side_effect=RuntimeError("provider down")))
    mapped = JSONResponse(
        status_code=503, content={"error": {"code": "provider_error", "message": "provider down"}}
    )

    with patch("omnidapter_server.services.crm_flows.map_library_exception", return_value=mapped):
        result = await execute_crm_operation(
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
async def test_execute_crm_operation_update_last_used_called() -> None:
    conn = _conn()
    crm_svc = SimpleNamespace(get_contact=AsyncMock(return_value={"id": "c-1"}))
    lib_conn = SimpleNamespace(crm=lambda: crm_svc)
    omni = SimpleNamespace(connection=AsyncMock(return_value=lib_conn))
    update_last_used = AsyncMock()
    session = AsyncMock()

    await execute_crm_operation(
        connection_id=str(conn.id),
        request=_request(),
        session=session,
        load_connection=AsyncMock(return_value=conn),
        build_omni=AsyncMock(return_value=omni),
        operation=lambda crm: crm.get_contact(),
        update_last_used=update_last_used,
    )

    update_last_used.assert_awaited_once_with(conn.id, session)


@pytest.mark.asyncio
async def test_execute_crm_operation_exception_skips_last_used() -> None:
    conn = _conn()
    omni = SimpleNamespace(connection=AsyncMock(side_effect=ValueError("bad")))
    update_last_used = AsyncMock()
    mapped = JSONResponse(status_code=400, content={"error": {"code": "x", "message": "y"}})

    with patch("omnidapter_server.services.crm_flows.map_library_exception", return_value=mapped):
        await execute_crm_operation(
            connection_id=str(conn.id),
            request=_request(),
            session=AsyncMock(),
            load_connection=AsyncMock(return_value=conn),
            build_omni=AsyncMock(return_value=omni),
            operation=AsyncMock(),
            update_last_used=update_last_used,
        )

    update_last_used.assert_not_awaited()
