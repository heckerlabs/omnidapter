"""Calendar service proxy endpoints."""

from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from omnidapter import (
    CreateEventRequest,
    GetAvailabilityRequest,
    Omnidapter,
    UpdateEventRequest,
)
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_api.config import Settings, get_settings
from omnidapter_api.database import get_session
from omnidapter_api.dependencies import (
    AuthContext,
    get_auth_context,
    get_encryption_service,
    get_request_id,
)
from omnidapter_api.encryption import EncryptionService
from omnidapter_api.errors import check_connection_status, map_library_exception
from omnidapter_api.models.connection import Connection
from omnidapter_api.services.connection_health import update_last_used
from omnidapter_api.services.usage import check_free_tier, is_billable_endpoint, record_usage
from omnidapter_api.stores.credential_store import DatabaseCredentialStore
from omnidapter_api.stores.oauth_state_store import DatabaseOAuthStateStore

router = APIRouter(tags=["calendar"])


def _build_omni(session: AsyncSession, encryption: EncryptionService) -> Omnidapter:
    cred_store = DatabaseCredentialStore(session=session, encryption=encryption)
    state_store = DatabaseOAuthStateStore(session=session, encryption=encryption)
    return Omnidapter(
        credential_store=cred_store,
        oauth_state_store=state_store,
        auto_refresh=True,
    )


async def _check_usage_and_get_conn(
    connection_id: str,
    auth: AuthContext,
    session: AsyncSession,
    settings: Settings,
    request: Request,
    endpoint: str,
) -> Connection | JSONResponse:
    """Validate connection, check status, enforce usage limits."""
    from sqlalchemy import select

    try:
        conn_uuid = uuid.UUID(connection_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "connection_not_found", "message": "Connection not found"},
        ) from exc

    result = await session.execute(
        select(Connection).where(
            Connection.id == conn_uuid,
            Connection.organization_id == auth.org_id,
        )
    )
    conn = result.scalar_one_or_none()
    if conn is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "connection_not_found", "message": "Connection not found"},
        )

    # Check connection status
    error = check_connection_status(conn.status, request)
    if error is not None:
        return error

    # Check free tier (only for billable endpoints)
    if is_billable_endpoint(endpoint):
        over_limit, usage = await check_free_tier(
            org_id=auth.org_id,
            plan=auth.plan,
            session=session,
            free_tier_calls=settings.omnidapter_free_tier_calls,
        )
        if over_limit:
            raise HTTPException(
                status_code=402,
                detail={
                    "code": "usage_limit_exceeded",
                    "message": "Free tier limit reached. Add a payment method to continue.",
                    "details": {
                        "limit": settings.omnidapter_free_tier_calls,
                        "used": usage,
                    },
                },
            )

    return conn


async def _record_and_respond(
    connection_id: uuid.UUID,
    org_id: uuid.UUID,
    provider_key: str,
    endpoint: str,
    status_code: int,
    start_time: float,
    session: AsyncSession,
    data: object,
    request_id: str,
) -> dict:
    """Record usage, update last_used, and return response."""
    duration_ms = int((time.time() - start_time) * 1000)
    await record_usage(
        org_id=org_id,
        connection_id=connection_id,
        endpoint=endpoint,
        provider_key=provider_key,
        response_status=status_code,
        duration_ms=duration_ms,
        session=session,
    )
    await update_last_used(connection_id, session)

    def _to_json_data(value: object) -> Any:
        if hasattr(value, "model_dump"):
            return cast(Any, value).model_dump(mode="json")
        return value

    if isinstance(data, list):
        return {
            "data": [_to_json_data(item) for item in data],
            "meta": {"request_id": request_id},
        }
    if hasattr(data, "model_dump"):
        return {"data": _to_json_data(data), "meta": {"request_id": request_id}}
    return {"data": data, "meta": {"request_id": request_id}}


# --- Calendar list/get ---


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
    endpoint = "calendar.list_calendars"
    conn = await _check_usage_and_get_conn(
        connection_id, auth, session, settings, request, endpoint
    )
    if isinstance(conn, JSONResponse):
        return conn
    omni = _build_omni(session, encryption)
    start = time.time()
    try:
        lib_conn = await omni.connection(connection_id)
        calendars = await lib_conn.calendar().list_calendars()
    except Exception as exc:
        return map_library_exception(exc, request)
    return await _record_and_respond(
        conn.id,
        auth.org_id,
        conn.provider_key,
        endpoint,
        200,
        start,
        session,
        calendars,
        request_id,
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
    endpoint = "calendar.list_events"
    conn = await _check_usage_and_get_conn(
        connection_id, auth, session, settings, request, endpoint
    )
    if isinstance(conn, JSONResponse):
        return conn
    omni = _build_omni(session, encryption)
    start_time = time.time()
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
    return await _record_and_respond(
        conn.id,
        auth.org_id,
        conn.provider_key,
        endpoint,
        200,
        start_time,
        session,
        events,
        request_id,
    )


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
    endpoint = "calendar.get_event"
    conn = await _check_usage_and_get_conn(
        connection_id, auth, session, settings, request, endpoint
    )
    if isinstance(conn, JSONResponse):
        return conn
    omni = _build_omni(session, encryption)
    start = time.time()
    try:
        lib_conn = await omni.connection(connection_id)
        event = await lib_conn.calendar().get_event(calendar_id=calendar_id, event_id=event_id)
    except Exception as exc:
        return map_library_exception(exc, request)
    return await _record_and_respond(
        conn.id, auth.org_id, conn.provider_key, endpoint, 200, start, session, event, request_id
    )


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
    endpoint = "calendar.create_event"
    conn = await _check_usage_and_get_conn(
        connection_id, auth, session, settings, request, endpoint
    )
    if isinstance(conn, JSONResponse):
        return conn
    omni = _build_omni(session, encryption)
    start = time.time()
    try:
        lib_conn = await omni.connection(connection_id)
        event = await lib_conn.calendar().create_event(body)
    except Exception as exc:
        return map_library_exception(exc, request)
    return await _record_and_respond(
        conn.id, auth.org_id, conn.provider_key, endpoint, 201, start, session, event, request_id
    )


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
    endpoint = "calendar.update_event"
    conn = await _check_usage_and_get_conn(
        connection_id, auth, session, settings, request, endpoint
    )
    if isinstance(conn, JSONResponse):
        return conn
    omni = _build_omni(session, encryption)
    start = time.time()
    try:
        lib_conn = await omni.connection(connection_id)
        # Inject IDs from path into the body
        update_req = body.model_copy(update={"event_id": event_id})
        event = await lib_conn.calendar().update_event(update_req)
    except Exception as exc:
        return map_library_exception(exc, request)
    return await _record_and_respond(
        conn.id, auth.org_id, conn.provider_key, endpoint, 200, start, session, event, request_id
    )


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
    endpoint = "calendar.delete_event"
    conn = await _check_usage_and_get_conn(
        connection_id, auth, session, settings, request, endpoint
    )
    if isinstance(conn, JSONResponse):
        return conn
    omni = _build_omni(session, encryption)
    start = time.time()
    try:
        lib_conn = await omni.connection(connection_id)
        await lib_conn.calendar().delete_event(calendar_id=calendar_id, event_id=event_id)
    except Exception as exc:
        return map_library_exception(exc, request)
    duration_ms = int((time.time() - start) * 1000)
    await record_usage(
        org_id=auth.org_id,
        connection_id=conn.id,
        endpoint=endpoint,
        provider_key=conn.provider_key,
        response_status=204,
        duration_ms=duration_ms,
        session=session,
    )
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
    endpoint = "calendar.get_availability"
    conn = await _check_usage_and_get_conn(
        connection_id, auth, session, settings, request, endpoint
    )
    if isinstance(conn, JSONResponse):
        return conn
    omni = _build_omni(session, encryption)
    start_time = time.time()
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
    return await _record_and_respond(
        conn.id,
        auth.org_id,
        conn.provider_key,
        endpoint,
        200,
        start_time,
        session,
        availability,
        request_id,
    )
