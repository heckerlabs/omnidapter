"""Calendar service proxy endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from omnidapter import (
    CreateEventRequest,
    GetAvailabilityRequest,
    Omnidapter,
    UpdateEventRequest,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_server.config import Settings, get_settings
from omnidapter_server.database import get_session
from omnidapter_server.dependencies import (
    AuthContext,
    get_auth_context,
    get_encryption_service,
    get_request_id,
)
from omnidapter_server.encryption import EncryptionService
from omnidapter_server.errors import check_connection_status, map_library_exception
from omnidapter_server.models.connection import Connection
from omnidapter_server.services.connection_health import update_last_used
from omnidapter_server.stores.credential_store import DatabaseCredentialStore
from omnidapter_server.stores.factory import build_oauth_state_store

router = APIRouter(tags=["calendar"])


def _build_omni(
    session: AsyncSession,
    encryption: EncryptionService,
    settings: Settings,
) -> Omnidapter:
    cred_store = DatabaseCredentialStore(session=session, encryption=encryption)
    state_store = build_oauth_state_store(settings, session, encryption)
    return Omnidapter(
        credential_store=cred_store,
        oauth_state_store=state_store,
        auto_refresh=True,
    )


async def _get_conn(
    connection_id: str,
    session: AsyncSession,
    request: Request,
) -> Connection:
    try:
        conn_uuid = uuid.UUID(connection_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "connection_not_found", "message": "Connection not found"},
        ) from exc

    result = await session.execute(select(Connection).where(Connection.id == conn_uuid))
    conn = result.scalar_one_or_none()
    if conn is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "connection_not_found", "message": "Connection not found"},
        )

    error = check_connection_status(conn.status, request)
    if error is not None:
        raise HTTPException(
            status_code=error.status_code,
            detail={"code": "connection_status_error", "message": "Connection not usable"},
        )

    return conn


def _wrap(data: object, request_id: str) -> dict:
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


@router.get("/connections/{connection_id}/calendar/calendars")
async def list_calendars(
    connection_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
):
    conn = await _get_conn(connection_id, session, request)
    omni = _build_omni(session, encryption, settings)
    try:
        lib_conn = await omni.connection(connection_id)
        calendars = await lib_conn.calendar().list_calendars()
    except Exception as exc:
        return map_library_exception(exc, request)
    await update_last_used(conn.id, session)
    return _wrap(calendars, request_id)


@router.get("/connections/{connection_id}/calendar/events")
async def list_events(
    connection_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
    calendar_id: str = Query(...),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    page_size: int | None = Query(None),
):
    conn = await _get_conn(connection_id, session, request)
    omni = _build_omni(session, encryption, settings)
    try:
        lib_conn = await omni.connection(connection_id)
        events = []
        async for event in lib_conn.calendar().list_events(
            calendar_id=calendar_id,
            time_min=start,
            time_max=end,
            page_size=page_size,
        ):
            events.append(event)
    except Exception as exc:
        return map_library_exception(exc, request)
    await update_last_used(conn.id, session)
    return _wrap(events, request_id)


@router.get("/connections/{connection_id}/calendar/events/{event_id}")
async def get_event(
    connection_id: str,
    event_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
    calendar_id: str = Query(...),
):
    conn = await _get_conn(connection_id, session, request)
    omni = _build_omni(session, encryption, settings)
    try:
        lib_conn = await omni.connection(connection_id)
        event = await lib_conn.calendar().get_event(calendar_id=calendar_id, event_id=event_id)
    except Exception as exc:
        return map_library_exception(exc, request)
    await update_last_used(conn.id, session)
    return _wrap(event, request_id)


@router.post("/connections/{connection_id}/calendar/events", status_code=201)
async def create_event(
    connection_id: str,
    body: CreateEventRequest,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
):
    conn = await _get_conn(connection_id, session, request)
    omni = _build_omni(session, encryption, settings)
    try:
        lib_conn = await omni.connection(connection_id)
        event = await lib_conn.calendar().create_event(body)
    except Exception as exc:
        return map_library_exception(exc, request)
    await update_last_used(conn.id, session)
    return _wrap(event, request_id)


@router.patch("/connections/{connection_id}/calendar/events/{event_id}")
async def update_event(
    connection_id: str,
    event_id: str,
    body: UpdateEventRequest,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
):
    conn = await _get_conn(connection_id, session, request)
    omni = _build_omni(session, encryption, settings)
    try:
        lib_conn = await omni.connection(connection_id)
        update_req = body.model_copy(update={"event_id": event_id})
        event = await lib_conn.calendar().update_event(update_req)
    except Exception as exc:
        return map_library_exception(exc, request)
    await update_last_used(conn.id, session)
    return _wrap(event, request_id)


@router.delete("/connections/{connection_id}/calendar/events/{event_id}", status_code=204)
async def delete_event(
    connection_id: str,
    event_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    calendar_id: str = Query(...),
):
    conn = await _get_conn(connection_id, session, request)
    omni = _build_omni(session, encryption, settings)
    try:
        lib_conn = await omni.connection(connection_id)
        await lib_conn.calendar().delete_event(calendar_id=calendar_id, event_id=event_id)
    except Exception as exc:
        return map_library_exception(exc, request)
    await update_last_used(conn.id, session)


@router.get("/connections/{connection_id}/calendar/availability")
async def get_availability(
    connection_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
    calendar_id: str = Query(...),
    start: datetime = Query(...),
    end: datetime = Query(...),
):
    conn = await _get_conn(connection_id, session, request)
    omni = _build_omni(session, encryption, settings)
    avail_req = GetAvailabilityRequest(
        calendar_ids=[calendar_id],
        time_min=start,
        time_max=end,
    )
    try:
        lib_conn = await omni.connection(connection_id)
        availability = await lib_conn.calendar().get_availability(avail_req)
    except Exception as exc:
        return map_library_exception(exc, request)
    await update_last_used(conn.id, session)
    return _wrap(availability, request_id)
