"""Shared CRM endpoint orchestration flows."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_server.errors import map_library_exception
from omnidapter_server.models.connection import Connection

ConnectionByUuidLoader = Callable[[uuid.UUID, AsyncSession], Awaitable[Connection | None]]
OmniBuilder = Callable[[AsyncSession, str], Awaitable[Any]]
CrmOperation = Callable[[Any], Awaitable[Any]]
LastUsedUpdater = Callable[[uuid.UUID, AsyncSession], Awaitable[None]]


async def execute_crm_operation(
    *,
    connection_id: str,
    request: Request,
    session: AsyncSession,
    load_connection: Callable[[str, AsyncSession, Request], Awaitable[Connection]],
    build_omni: OmniBuilder,
    operation: CrmOperation,
    update_last_used: LastUsedUpdater,
) -> Any:
    conn = await load_connection(connection_id, session, request)
    omni = await build_omni(session, conn.provider_key)
    try:
        lib_conn = await omni.connection(connection_id)
        result = await operation(lib_conn.crm())
    except Exception as exc:
        return map_library_exception(exc, request)

    await update_last_used(conn.id, session)
    return result
