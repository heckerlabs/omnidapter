"""Calendar service proxy endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from omnidapter import (
    CreateCalendarRequest,
    CreateEventRequest,
    GetAvailabilityRequest,
    Omnidapter,
    UpdateCalendarRequest,
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
from omnidapter_server.errors import check_connection_status
from omnidapter_server.models.connection import Connection
from omnidapter_server.services.calendar_flows import (
    execute_calendar_operation,
    get_connection_ready_or_404,
    wrap_response,
)
from omnidapter_server.services.connection_health import update_last_used
from omnidapter_server.stores.credential_store import DatabaseCredentialStore
from omnidapter_server.stores.factory import build_oauth_state_store

router = APIRouter(tags=["calendar"])


async def _build_omni(
    session: AsyncSession,
    encryption: EncryptionService,
    settings: Settings,
    provider_key: str,
) -> Omnidapter:
    cred_store = DatabaseCredentialStore(session=session, encryption=encryption)
    state_store = build_oauth_state_store(settings, session, encryption)
    return Omnidapter(
        credential_store=cred_store,
        oauth_state_store=state_store,
        auto_refresh=True,
    )


async def _load_connection_by_uuid(
    conn_uuid: uuid.UUID, session: AsyncSession
) -> Connection | None:
    result = await session.execute(select(Connection).where(Connection.id == conn_uuid))
    return result.scalar_one_or_none()


async def _get_conn(
    connection_id: str,
    session: AsyncSession,
    request: Request,
) -> Connection:
    return await get_connection_ready_or_404(
        connection_id=connection_id,
        session=session,
        request=request,
        load_connection_by_uuid=_load_connection_by_uuid,
        check_status=check_connection_status,
    )


def _wrap(data: object, request_id: str) -> dict:
    return wrap_response(data, request_id)


def _respond(data: object, request_id: str):
    if isinstance(data, Response):
        return data
    return _wrap(data, request_id)


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
    result = await execute_calendar_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda cal: cal.list_calendars(),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


@router.get("/connections/{connection_id}/calendar/calendars/{calendar_id}")
async def get_calendar(
    connection_id: str,
    calendar_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
):
    result = await execute_calendar_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda cal: cal.get_calendar(calendar_id=calendar_id),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


@router.post("/connections/{connection_id}/calendar/calendars", status_code=201)
async def create_calendar(
    connection_id: str,
    body: CreateCalendarRequest,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
):
    result = await execute_calendar_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda cal: cal.create_calendar(body),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


@router.patch("/connections/{connection_id}/calendar/calendars/{calendar_id}")
async def update_calendar(
    connection_id: str,
    calendar_id: str,
    body: UpdateCalendarRequest,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
):
    result = await execute_calendar_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda cal: cal.update_calendar(body.model_copy(update={"calendar_id": calendar_id})),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


@router.delete("/connections/{connection_id}/calendar/calendars/{calendar_id}", status_code=204)
async def delete_calendar(
    connection_id: str,
    calendar_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    await execute_calendar_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda cal: cal.delete_calendar(calendar_id=calendar_id),
        update_last_used=update_last_used,
    )


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
    async def _op(cal):
        events = []
        async for event in cal.list_events(
            calendar_id=calendar_id,
            time_min=start,
            time_max=end,
            page_size=page_size,
        ):
            events.append(event)
        return events

    result = await execute_calendar_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=_op,
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


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
    result = await execute_calendar_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda cal: cal.get_event(calendar_id=calendar_id, event_id=event_id),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


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
    result = await execute_calendar_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda cal: cal.create_event(body),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


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
    result = await execute_calendar_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda cal: cal.update_event(body.model_copy(update={"event_id": event_id})),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


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
    await execute_calendar_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda cal: cal.delete_event(calendar_id=calendar_id, event_id=event_id),
        update_last_used=update_last_used,
    )


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
    avail_req = GetAvailabilityRequest(
        calendar_ids=[calendar_id],
        time_min=start,
        time_max=end,
    )
    result = await execute_calendar_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda cal: cal.get_availability(avail_req),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)
