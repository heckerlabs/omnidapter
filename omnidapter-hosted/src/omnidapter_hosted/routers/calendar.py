"""Hosted calendar proxy endpoints with tenant-scoped connection access."""

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
from omnidapter_server.database import get_session
from omnidapter_server.encryption import EncryptionService
from omnidapter_server.models.connection import Connection
from omnidapter_server.services.calendar_flows import (
    execute_calendar_operation,
    get_connection_ready_or_404,
    wrap_response,
)
from omnidapter_server.services.connection_health import update_last_used
from omnidapter_server.stores.credential_store import DatabaseCredentialStore
from omnidapter_server.stores.factory import build_oauth_state_store
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_hosted.config import HostedSettings, get_hosted_settings
from omnidapter_hosted.dependencies import (
    HostedAuthContext,
    get_encryption_service,
    get_hosted_auth_context,
    get_request_id,
)
from omnidapter_hosted.models.connection_owner import HostedConnectionOwner
from omnidapter_hosted.services.provider_registry import build_hosted_provider_registry

router = APIRouter(tags=["calendar"])


async def _build_omni(
    session: AsyncSession,
    encryption: EncryptionService,
    settings: HostedSettings,
    tenant_id: uuid.UUID,
    provider_key: str,
) -> Omnidapter:
    cred_store = DatabaseCredentialStore(session=session, encryption=encryption)
    state_store = build_oauth_state_store(settings, session, encryption)
    registry = await build_hosted_provider_registry(
        tenant_id=tenant_id,
        provider_key=provider_key,
        session=session,
        settings=settings,
        encryption=encryption,
    )
    return Omnidapter(
        credential_store=cred_store,
        oauth_state_store=state_store,
        registry=registry,
        auto_refresh=True,
    )


async def _load_connection_by_uuid(
    conn_uuid: uuid.UUID,
    session: AsyncSession,
    tenant_id: uuid.UUID,
) -> Connection | None:
    result = await session.execute(
        select(Connection)
        .join(HostedConnectionOwner, HostedConnectionOwner.connection_id == Connection.id)
        .where(Connection.id == conn_uuid, HostedConnectionOwner.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def _get_conn(
    connection_id: str,
    session: AsyncSession,
    request: Request,
    tenant_id: uuid.UUID,
) -> Connection:
    return await get_connection_ready_or_404(
        connection_id=connection_id,
        session=session,
        request=request,
        load_connection_by_uuid=lambda conn_uuid, s: _load_connection_by_uuid(
            conn_uuid, s, tenant_id
        ),
    )


def _wrap(data: object, request_id: str) -> dict:
    return wrap_response(data, request_id)


def _respond(data: object, request_id: str):
    if isinstance(data, Response):
        return data
    return _wrap(data, request_id)


@router.get("/connections/{connection_id}/calendars")
async def list_calendars(
    connection_id: str,
    request: Request,
    auth: Annotated[HostedAuthContext, Depends(get_hosted_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: HostedSettings = Depends(get_hosted_settings),
    request_id: str = Depends(get_request_id),
):
    result = await execute_calendar_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=lambda conn_id, s, req: _get_conn(conn_id, s, req, auth.tenant_id),
        build_omni=lambda s, provider_key: _build_omni(
            s,
            encryption,
            settings,
            auth.tenant_id,
            provider_key,
        ),
        operation=lambda cal: cal.list_calendars(),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


@router.get("/connections/{connection_id}/calendars/{calendar_id}")
async def get_calendar(
    connection_id: str,
    calendar_id: str,
    request: Request,
    auth: Annotated[HostedAuthContext, Depends(get_hosted_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: HostedSettings = Depends(get_hosted_settings),
    request_id: str = Depends(get_request_id),
):
    result = await execute_calendar_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=lambda conn_id, s, req: _get_conn(conn_id, s, req, auth.tenant_id),
        build_omni=lambda s, provider_key: _build_omni(
            s,
            encryption,
            settings,
            auth.tenant_id,
            provider_key,
        ),
        operation=lambda cal: cal.get_calendar(calendar_id=calendar_id),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


@router.post("/connections/{connection_id}/calendars", status_code=201)
async def create_calendar(
    connection_id: str,
    body: CreateCalendarRequest,
    request: Request,
    auth: Annotated[HostedAuthContext, Depends(get_hosted_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: HostedSettings = Depends(get_hosted_settings),
    request_id: str = Depends(get_request_id),
):
    result = await execute_calendar_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=lambda conn_id, s, req: _get_conn(conn_id, s, req, auth.tenant_id),
        build_omni=lambda s, provider_key: _build_omni(
            s,
            encryption,
            settings,
            auth.tenant_id,
            provider_key,
        ),
        operation=lambda cal: cal.create_calendar(body),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


@router.patch("/connections/{connection_id}/calendars/{calendar_id}")
async def update_calendar(
    connection_id: str,
    calendar_id: str,
    body: UpdateCalendarRequest,
    request: Request,
    auth: Annotated[HostedAuthContext, Depends(get_hosted_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: HostedSettings = Depends(get_hosted_settings),
    request_id: str = Depends(get_request_id),
):
    result = await execute_calendar_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=lambda conn_id, s, req: _get_conn(conn_id, s, req, auth.tenant_id),
        build_omni=lambda s, provider_key: _build_omni(
            s,
            encryption,
            settings,
            auth.tenant_id,
            provider_key,
        ),
        operation=lambda cal: cal.update_calendar(
            body.model_copy(update={"calendar_id": calendar_id})
        ),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


@router.delete("/connections/{connection_id}/calendars/{calendar_id}", status_code=204)
async def delete_calendar(
    connection_id: str,
    calendar_id: str,
    request: Request,
    auth: Annotated[HostedAuthContext, Depends(get_hosted_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: HostedSettings = Depends(get_hosted_settings),
):
    await execute_calendar_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=lambda conn_id, s, req: _get_conn(conn_id, s, req, auth.tenant_id),
        build_omni=lambda s, provider_key: _build_omni(
            s,
            encryption,
            settings,
            auth.tenant_id,
            provider_key,
        ),
        operation=lambda cal: cal.delete_calendar(calendar_id=calendar_id),
        update_last_used=update_last_used,
    )


@router.get("/connections/{connection_id}/calendars/{calendar_id}/events")
async def list_events(
    connection_id: str,
    calendar_id: str,
    request: Request,
    auth: Annotated[HostedAuthContext, Depends(get_hosted_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: HostedSettings = Depends(get_hosted_settings),
    request_id: str = Depends(get_request_id),
    start: datetime | None = Query(
        None,
        description="Filter events starting after this time (ISO 8601, e.g., 2026-04-06T10:00:00Z)",
    ),
    end: datetime | None = Query(
        None,
        description="Filter events ending before this time (ISO 8601, e.g., 2026-04-06T18:00:00Z)",
    ),
    limit: int = Query(
        100, ge=1, le=1000, description="Maximum number of events to return per page"
    ),
    offset: int = Query(0, ge=0, description="Number of events to skip before returning results"),
):
    async def _op(cal):
        events = []
        skipped = 0
        has_more = False
        async for event in cal.list_events(
            calendar_id=calendar_id,
            time_min=start,
            time_max=end,
            page_size=limit + 1,
        ):
            if skipped < offset:
                skipped += 1
                continue
            events.append(event)
            if len(events) > limit:
                has_more = True
                events = events[:limit]
                break
        return events, has_more

    result = await execute_calendar_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=lambda conn_id, s, req: _get_conn(conn_id, s, req, auth.tenant_id),
        build_omni=lambda s, provider_key: _build_omni(
            s,
            encryption,
            settings,
            auth.tenant_id,
            provider_key,
        ),
        operation=_op,
        update_last_used=update_last_used,
    )
    if isinstance(result, Response):
        return result
    # Handle both tuple (normal case) and list (test mocks)
    if isinstance(result, tuple):
        events, has_more = result
    else:
        events, has_more = result, False
    serialized_events = [
        event.model_dump(mode="json") if hasattr(event, "model_dump") else event for event in events
    ]
    return {
        "data": serialized_events,
        "meta": {
            "request_id": request_id,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "count": len(serialized_events),
                "has_more": has_more,
            },
        },
    }


@router.get("/connections/{connection_id}/calendars/{calendar_id}/events/{event_id}")
async def get_event(
    connection_id: str,
    calendar_id: str,
    event_id: str,
    request: Request,
    auth: Annotated[HostedAuthContext, Depends(get_hosted_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: HostedSettings = Depends(get_hosted_settings),
    request_id: str = Depends(get_request_id),
):
    result = await execute_calendar_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=lambda conn_id, s, req: _get_conn(conn_id, s, req, auth.tenant_id),
        build_omni=lambda s, provider_key: _build_omni(
            s,
            encryption,
            settings,
            auth.tenant_id,
            provider_key,
        ),
        operation=lambda cal: cal.get_event(calendar_id=calendar_id, event_id=event_id),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


@router.post("/connections/{connection_id}/calendars/{calendar_id}/events", status_code=201)
async def create_event(
    connection_id: str,
    calendar_id: str,
    body: CreateEventRequest,
    request: Request,
    auth: Annotated[HostedAuthContext, Depends(get_hosted_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: HostedSettings = Depends(get_hosted_settings),
    request_id: str = Depends(get_request_id),
):
    result = await execute_calendar_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=lambda conn_id, s, req: _get_conn(conn_id, s, req, auth.tenant_id),
        build_omni=lambda s, provider_key: _build_omni(
            s,
            encryption,
            settings,
            auth.tenant_id,
            provider_key,
        ),
        operation=lambda cal: cal.create_event(
            body.model_copy(update={"calendar_id": calendar_id})
        ),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


@router.patch("/connections/{connection_id}/calendars/{calendar_id}/events/{event_id}")
async def update_event(
    connection_id: str,
    calendar_id: str,
    event_id: str,
    body: UpdateEventRequest,
    request: Request,
    auth: Annotated[HostedAuthContext, Depends(get_hosted_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: HostedSettings = Depends(get_hosted_settings),
    request_id: str = Depends(get_request_id),
):
    result = await execute_calendar_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=lambda conn_id, s, req: _get_conn(conn_id, s, req, auth.tenant_id),
        build_omni=lambda s, provider_key: _build_omni(
            s,
            encryption,
            settings,
            auth.tenant_id,
            provider_key,
        ),
        operation=lambda cal: cal.update_event(
            body.model_copy(update={"calendar_id": calendar_id, "event_id": event_id})
        ),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


@router.delete(
    "/connections/{connection_id}/calendars/{calendar_id}/events/{event_id}", status_code=204
)
async def delete_event(
    connection_id: str,
    calendar_id: str,
    event_id: str,
    request: Request,
    auth: Annotated[HostedAuthContext, Depends(get_hosted_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: HostedSettings = Depends(get_hosted_settings),
):
    await execute_calendar_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=lambda conn_id, s, req: _get_conn(conn_id, s, req, auth.tenant_id),
        build_omni=lambda s, provider_key: _build_omni(
            s,
            encryption,
            settings,
            auth.tenant_id,
            provider_key,
        ),
        operation=lambda cal: cal.delete_event(calendar_id=calendar_id, event_id=event_id),
        update_last_used=update_last_used,
    )


@router.get("/connections/{connection_id}/calendars/{calendar_id}/availability")
async def get_availability(
    connection_id: str,
    calendar_id: str,
    request: Request,
    auth: Annotated[HostedAuthContext, Depends(get_hosted_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: HostedSettings = Depends(get_hosted_settings),
    request_id: str = Depends(get_request_id),
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
        load_connection=lambda conn_id, s, req: _get_conn(conn_id, s, req, auth.tenant_id),
        build_omni=lambda s, provider_key: _build_omni(
            s,
            encryption,
            settings,
            auth.tenant_id,
            provider_key,
        ),
        operation=lambda cal: cal.get_availability(avail_req),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)
