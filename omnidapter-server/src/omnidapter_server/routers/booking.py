"""Booking service proxy endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from omnidapter import (
    AvailabilitySlot,
    Booking,
    BookingCustomer,
    BookingLocation,
    CreateBookingRequest,
    FindCustomerRequest,
    ListBookingsRequest,
    Omnidapter,
    RescheduleBookingRequest,
    ServiceType,
    StaffMember,
    UpdateBookingRequest,
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
from omnidapter_server.provider_registry import build_provider_registry
from omnidapter_server.schemas.common import ApiResponse
from omnidapter_server.services.booking_flows import execute_booking_operation
from omnidapter_server.services.calendar_flows import get_connection_ready_or_404
from omnidapter_server.services.connection_health import update_last_used
from omnidapter_server.services.response_utils import wrap_response
from omnidapter_server.stores.credential_store import DatabaseCredentialStore
from omnidapter_server.stores.factory import build_oauth_state_store

router = APIRouter(tags=["booking"])


async def _build_omni(
    session: AsyncSession,
    encryption: EncryptionService,
    settings: Settings,
    provider_key: str,
) -> Omnidapter:
    cred_store = DatabaseCredentialStore(session=session, encryption=encryption)
    state_store = build_oauth_state_store(settings, session, encryption)
    registry = build_provider_registry(settings)
    return Omnidapter(
        credential_store=cred_store,
        oauth_state_store=state_store,
        registry=registry,
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


# ── Services ──────────────────────────────────────────────────────────────────


@router.get(
    "/connections/{connection_id}/booking/services",
    operation_id="booking_list_services",
    response_model=ApiResponse[list[ServiceType]],
)
async def list_booking_services(
    connection_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
    location_id: str | None = Query(None),
):
    result = await execute_booking_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda bk: bk.list_services(location_id=location_id),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


@router.get(
    "/connections/{connection_id}/booking/services/{service_id}",
    operation_id="booking_get_service",
    response_model=ApiResponse[ServiceType],
)
async def get_booking_service(
    connection_id: str,
    service_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
):
    result = await execute_booking_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda bk: bk.get_service_type(service_id=service_id),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


# ── Staff ─────────────────────────────────────────────────────────────────────


@router.get(
    "/connections/{connection_id}/booking/staff",
    operation_id="booking_list_staff",
    response_model=ApiResponse[list[StaffMember]],
)
async def list_booking_staff(
    connection_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
    service_id: str | None = Query(None),
    location_id: str | None = Query(None),
):
    result = await execute_booking_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda bk: bk.list_staff(service_id=service_id, location_id=location_id),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


@router.get(
    "/connections/{connection_id}/booking/staff/{staff_id}",
    operation_id="booking_get_staff_member",
    response_model=ApiResponse[StaffMember],
)
async def get_booking_staff_member(
    connection_id: str,
    staff_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
):
    result = await execute_booking_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda bk: bk.get_staff(staff_id=staff_id),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


# ── Locations ─────────────────────────────────────────────────────────────────


@router.get(
    "/connections/{connection_id}/booking/locations",
    operation_id="booking_list_locations",
    response_model=ApiResponse[list[BookingLocation]],
)
async def list_booking_locations(
    connection_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
):
    result = await execute_booking_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda bk: bk.list_locations(),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


# ── Availability ──────────────────────────────────────────────────────────────


@router.get(
    "/connections/{connection_id}/booking/availability",
    operation_id="booking_availability",
    response_model=ApiResponse[list[AvailabilitySlot]],
)
async def get_booking_availability(
    connection_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
    service_id: str = Query(...),
    start: datetime = Query(...),
    end: datetime = Query(...),
    staff_id: str | None = Query(None),
    location_id: str | None = Query(None),
    timezone: str | None = Query(None),
):
    result = await execute_booking_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda bk: bk.get_availability(
            service_id=service_id,
            start=start,
            end=end,
            staff_id=staff_id,
            location_id=location_id,
            timezone=timezone,
        ),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


# ── Appointments ──────────────────────────────────────────────────────────────


@router.post(
    "/connections/{connection_id}/booking/appointments",
    status_code=201,
    operation_id="booking_create_booking",
    response_model=ApiResponse[Booking],
)
async def create_booking(
    connection_id: str,
    body: CreateBookingRequest,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
):
    result = await execute_booking_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda bk: bk.create_booking(body),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


@router.get(
    "/connections/{connection_id}/booking/appointments",
    operation_id="booking_list_bookings",
    response_model=ApiResponse[list[Booking]],
)
async def list_bookings(
    connection_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    staff_id: str | None = Query(None),
    service_id: str | None = Query(None),
    location_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    list_req = ListBookingsRequest(
        start=start,
        end=end,
        staff_id=staff_id,
        service_id=service_id,
        location_id=location_id,
        page_size=limit,
    )

    async def _op(bk):
        items = []
        async for booking in bk.list_bookings(list_req):
            items.append(booking)
            if len(items) >= limit:
                break
        return items

    result = await execute_booking_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=_op,
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


@router.get(
    "/connections/{connection_id}/booking/appointments/{appointment_id}",
    operation_id="booking_get_booking",
    response_model=ApiResponse[Booking],
)
async def get_booking(
    connection_id: str,
    appointment_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
):
    result = await execute_booking_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda bk: bk.get_booking(booking_id=appointment_id),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


@router.patch(
    "/connections/{connection_id}/booking/appointments/{appointment_id}",
    operation_id="booking_update_booking",
    response_model=ApiResponse[Booking],
)
async def update_booking(
    connection_id: str,
    appointment_id: str,
    body: UpdateBookingRequest,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
):
    result = await execute_booking_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda bk: bk.update_booking(
            body.model_copy(update={"booking_id": appointment_id})
        ),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


@router.delete(
    "/connections/{connection_id}/booking/appointments/{appointment_id}",
    status_code=204,
    operation_id="booking_cancel_booking",
)
async def cancel_booking(
    connection_id: str,
    appointment_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    reason: str | None = Query(None),
):
    await execute_booking_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda bk: bk.cancel_booking(booking_id=appointment_id, reason=reason),
        update_last_used=update_last_used,
    )


@router.post(
    "/connections/{connection_id}/booking/appointments/{appointment_id}/reschedule",
    operation_id="booking_reschedule_booking",
    response_model=ApiResponse[Booking],
)
async def reschedule_booking(
    connection_id: str,
    appointment_id: str,
    body: RescheduleBookingRequest,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
):
    result = await execute_booking_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda bk: bk.reschedule_booking(
            body.model_copy(update={"booking_id": appointment_id})
        ),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


# ── Customers ─────────────────────────────────────────────────────────────────


@router.get(
    "/connections/{connection_id}/booking/customers/search",
    operation_id="booking_find_customer",
    response_model=ApiResponse[BookingCustomer | None],
)
async def find_booking_customer(
    connection_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
    email: str | None = Query(None),
    phone: str | None = Query(None),
    name: str | None = Query(None),
):
    find_req = FindCustomerRequest(email=email, phone=phone, name=name)
    result = await execute_booking_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda bk: bk.find_customer(find_req),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


@router.get(
    "/connections/{connection_id}/booking/customers/{customer_id}",
    operation_id="booking_get_customer",
    response_model=ApiResponse[BookingCustomer],
)
async def get_booking_customer(
    connection_id: str,
    customer_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
):
    result = await execute_booking_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda bk: bk.get_customer(customer_id=customer_id),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


@router.post(
    "/connections/{connection_id}/booking/customers",
    status_code=201,
    operation_id="booking_create_customer",
    response_model=ApiResponse[BookingCustomer],
)
async def create_booking_customer(
    connection_id: str,
    body: BookingCustomer,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
):
    result = await execute_booking_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda bk: bk.create_customer(body),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)
