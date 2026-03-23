"""Shared calendar endpoint orchestration flows."""

from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_server.errors import check_connection_status, map_library_exception
from omnidapter_server.models.connection import Connection

ConnectionByUuidLoader = Callable[[uuid.UUID, AsyncSession], Awaitable[Connection | None]]
OmniBuilder = Callable[[AsyncSession, str], Awaitable[Any]]
CalendarOperation = Callable[[Any], Awaitable[Any]]
LastUsedUpdater = Callable[[uuid.UUID, AsyncSession], Awaitable[None]]
StatusChecker = Callable[[str, Request], Any]


def wrap_response(data: object, request_id: str) -> dict:
    if isinstance(data, list):
        return {
            "data": [
                item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                for item in data
            ],
            "meta": {"request_id": request_id},
        }
    if hasattr(data, "model_dump"):
        return {"data": data.model_dump(mode="json"), "meta": {"request_id": request_id}}  # type: ignore[union-attr]
    return {"data": data, "meta": {"request_id": request_id}}


async def get_connection_ready_or_404(
    *,
    connection_id: str,
    session: AsyncSession,
    request: Request,
    load_connection_by_uuid: ConnectionByUuidLoader,
    check_status: StatusChecker = check_connection_status,
) -> Connection:
    try:
        conn_uuid = uuid.UUID(connection_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "connection_not_found", "message": "Connection not found"},
        ) from exc

    conn = await load_connection_by_uuid(conn_uuid, session)
    if conn is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "connection_not_found", "message": "Connection not found"},
        )

    error = check_status(conn.status, request)
    if error is not None:
        body = json.loads(bytes(error.body))
        raise HTTPException(status_code=error.status_code, detail=body["error"])

    return conn


async def execute_calendar_operation(
    *,
    connection_id: str,
    request: Request,
    session: AsyncSession,
    load_connection: Callable[[str, AsyncSession, Request], Awaitable[Connection]],
    build_omni: OmniBuilder,
    operation: CalendarOperation,
    update_last_used: LastUsedUpdater,
) -> Any:
    conn = await load_connection(connection_id, session, request)
    omni = await build_omni(session, conn.provider_key)
    try:
        lib_conn = await omni.connection(connection_id)
        result = await operation(lib_conn.calendar())
    except Exception as exc:
        return map_library_exception(exc, request)

    await update_last_used(conn.id, session)
    return result
