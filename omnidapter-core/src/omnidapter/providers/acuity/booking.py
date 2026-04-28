"""Acuity Scheduling booking service implementation."""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from datetime import datetime
from typing import Any

from omnidapter.auth.models import OAuth2Credentials
from omnidapter.providers.acuity import mappers
from omnidapter.services.booking.capabilities import BookingCapability
from omnidapter.services.booking.interface import BookingService
from omnidapter.services.booking.models import (
    AvailabilitySlot,
    Booking,
    BookingCustomer,
    BookingLocation,
    ServiceType,
    StaffMember,
)
from omnidapter.services.booking.requests import (
    CreateBookingRequest,
    FindCustomerRequest,
    ListBookingsRequest,
    RescheduleBookingRequest,
    UpdateBookingRequest,
)
from omnidapter.stores.credentials import StoredCredential
from omnidapter.transport.client import OmnidapterHttpClient
from omnidapter.transport.retry import RetryPolicy

ACUITY_API_BASE = "https://acuityscheduling.com/api/v1"

_ACUITY_CAPABILITIES = frozenset(
    {
        BookingCapability.LIST_SERVICES,
        BookingCapability.LIST_STAFF,
        BookingCapability.GET_AVAILABILITY,
        BookingCapability.CREATE_BOOKING,
        BookingCapability.CANCEL_BOOKING,
        BookingCapability.RESCHEDULE_BOOKING,
        BookingCapability.UPDATE_BOOKING,
        BookingCapability.LIST_BOOKINGS,
        BookingCapability.CUSTOMER_LOOKUP,
        BookingCapability.CUSTOMER_MANAGEMENT,
        BookingCapability.MULTI_STAFF,
    }
)


class AcuityBookingService(BookingService):
    """Acuity Scheduling API v1 booking service."""

    def __init__(
        self,
        connection_id: str,
        stored_credential: StoredCredential,
        retry_policy: RetryPolicy | None = None,
        hooks: Any = None,
    ) -> None:
        self._connection_id = connection_id
        self._stored = stored_credential
        self._http = OmnidapterHttpClient(
            provider_key="acuity",
            retry_policy=retry_policy,
            hooks=hooks,
        )

    @property
    def capabilities(self) -> frozenset[BookingCapability]:
        return _ACUITY_CAPABILITIES

    @property
    def _provider_key(self) -> str:
        return "acuity"

    async def _resolve_stored_credential(self) -> StoredCredential:
        resolver = getattr(self, "_credential_resolver", None)
        if resolver is None:
            return self._stored
        self._stored = await resolver(self._connection_id)
        return self._stored

    async def _auth_headers(self) -> dict[str, str]:
        creds = (await self._resolve_stored_credential()).credentials
        if isinstance(creds, OAuth2Credentials):
            return {"Authorization": f"Bearer {creds.access_token}"}
        return {}

    async def list_services(self, location_id: str | None = None) -> list[ServiceType]:
        resp = await self._http.request(
            "GET",
            f"{ACUITY_API_BASE}/appointment-types",
            headers=await self._auth_headers(),
        )
        return [mappers.to_service_type(item) for item in resp.json()]

    async def get_service_type(self, service_id: str) -> ServiceType:
        resp = await self._http.request(
            "GET",
            f"{ACUITY_API_BASE}/appointment-types/{service_id}",
            headers=await self._auth_headers(),
        )
        return mappers.to_service_type(resp.json())

    async def list_staff(
        self,
        service_id: str | None = None,
        location_id: str | None = None,
    ) -> list[StaffMember]:
        resp = await self._http.request(
            "GET",
            f"{ACUITY_API_BASE}/calendars",
            headers=await self._auth_headers(),
        )
        return [mappers.to_staff_member(item) for item in resp.json()]

    async def get_staff(self, staff_id: str) -> StaffMember:
        all_staff = await self.list_staff()
        for member in all_staff:
            if member.id == staff_id:
                return member
        from omnidapter.core.errors import ProviderAPIError
        from omnidapter.transport.correlation import new_correlation_id

        raise ProviderAPIError(
            f"Staff member {staff_id!r} not found",
            provider_key="acuity",
            status_code=404,
            correlation_id=new_correlation_id(),
        )

    async def list_locations(self) -> list[BookingLocation]:
        self._require_capability(BookingCapability.LIST_LOCATIONS)
        return []  # unreachable

    async def get_availability(
        self,
        service_id: str,
        start: datetime,
        end: datetime,
        staff_id: str | None = None,
        location_id: str | None = None,
        timezone: str | None = None,
    ) -> list[AvailabilitySlot]:
        svc = await self.get_service_type(service_id)
        duration_minutes = svc.duration_minutes or 60

        # Enumerate months in the range
        months: list[str] = []
        d = start.date().replace(day=1)
        end_month = end.date().replace(day=1)
        while d <= end_month:
            months.append(d.strftime("%Y-%m"))
            if d.month == 12:
                d = d.replace(year=d.year + 1, month=1)
            else:
                d = d.replace(month=d.month + 1)

        headers = await self._auth_headers()
        available_dates: list[str] = []
        for month in months:
            params: dict[str, Any] = {"month": month, "appointmentTypeID": service_id}
            if staff_id:
                params["calendarID"] = staff_id
            if timezone:
                params["timezone"] = timezone
            resp = await self._http.request(
                "GET",
                f"{ACUITY_API_BASE}/availability/dates",
                headers=headers,
                params=params,
            )
            available_dates.extend(resp.json())

        slots: list[AvailabilitySlot] = []
        for date_str in available_dates:
            params = {"date": date_str, "appointmentTypeID": service_id}
            if staff_id:
                params["calendarID"] = staff_id
            if timezone:
                params["timezone"] = timezone
            resp = await self._http.request(
                "GET",
                f"{ACUITY_API_BASE}/availability/times",
                headers=headers,
                params=params,
            )
            for item in resp.json():
                if not item.get("slotsAvailable", 1):
                    continue
                slot = mappers.to_availability_slot(item, service_id, duration_minutes, staff_id)
                if start <= slot.start <= end:
                    slots.append(slot)
        return slots

    async def create_booking(self, request: CreateBookingRequest) -> Booking:
        customer = request.customer
        name_parts = (customer.name or "").split(" ", 1)
        body: dict[str, Any] = {
            "appointmentTypeID": int(request.service_id),
            "datetime": request.start.isoformat(),
            "firstName": name_parts[0],
            "lastName": name_parts[1] if len(name_parts) > 1 else "",
        }
        if customer.email:
            body["email"] = customer.email
        if customer.phone:
            body["phone"] = customer.phone
        if request.staff_id:
            body["calendarID"] = int(request.staff_id)
        if request.notes:
            body["notes"] = request.notes
        resp = await self._http.request(
            "POST",
            f"{ACUITY_API_BASE}/appointments",
            headers=await self._auth_headers(),
            json=body,
        )
        return mappers.to_booking(resp.json())

    async def get_booking(self, booking_id: str) -> Booking:
        resp = await self._http.request(
            "GET",
            f"{ACUITY_API_BASE}/appointments/{booking_id}",
            headers=await self._auth_headers(),
        )
        return mappers.to_booking(resp.json())

    def list_bookings(self, request: ListBookingsRequest) -> AsyncIterator[Booking]:
        return self._iter_bookings(request)

    async def _iter_bookings(self, request: ListBookingsRequest) -> AsyncGenerator[Booking, None]:
        params: dict[str, Any] = {}
        if request.start:
            params["minDate"] = request.start.date().isoformat()
        if request.end:
            params["maxDate"] = request.end.date().isoformat()
        if request.status:
            params["status"] = request.status.value
        if request.customer_email:
            params["email"] = request.customer_email
        if request.staff_id:
            params["calendarID"] = request.staff_id
        if request.service_id:
            params["appointmentTypeID"] = request.service_id

        page_size = request.page_size or 100
        params["max"] = page_size
        offset = 0
        headers = await self._auth_headers()
        while True:
            params["offset"] = offset
            resp = await self._http.request(
                "GET",
                f"{ACUITY_API_BASE}/appointments",
                headers=headers,
                params=params,
            )
            data = resp.json()
            if not data:
                break
            for item in data:
                yield mappers.to_booking(item)
            if len(data) < page_size:
                break
            offset += page_size

    async def update_booking(self, request: UpdateBookingRequest) -> Booking:
        body: dict[str, Any] = {}
        if request.start:
            body["datetime"] = request.start.isoformat()
        if request.staff_id:
            body["calendarID"] = int(request.staff_id)
        if request.notes is not None:
            body["notes"] = request.notes
        resp = await self._http.request(
            "PUT",
            f"{ACUITY_API_BASE}/appointments/{request.booking_id}",
            headers=await self._auth_headers(),
            json=body,
        )
        return mappers.to_booking(resp.json())

    async def cancel_booking(self, booking_id: str, reason: str | None = None) -> None:
        await self._http.request(
            "DELETE",
            f"{ACUITY_API_BASE}/appointments/{booking_id}",
            headers=await self._auth_headers(),
        )

    async def reschedule_booking(self, request: RescheduleBookingRequest) -> Booking:
        body: dict[str, Any] = {"datetime": request.new_start.isoformat()}
        if request.new_staff_id:
            body["calendarID"] = int(request.new_staff_id)
        resp = await self._http.request(
            "PUT",
            f"{ACUITY_API_BASE}/appointments/{request.booking_id}",
            headers=await self._auth_headers(),
            json=body,
        )
        return mappers.to_booking(resp.json())

    async def find_customer(self, request: FindCustomerRequest) -> BookingCustomer | None:
        params: dict[str, Any] = {}
        if request.email:
            params["email"] = request.email
        elif request.phone:
            params["phone"] = request.phone
        else:
            return None
        resp = await self._http.request(
            "GET",
            f"{ACUITY_API_BASE}/clients",
            headers=await self._auth_headers(),
            params=params,
        )
        data = resp.json()
        if data:
            return mappers.to_booking_customer(data[0])
        return None

    async def get_customer(self, customer_id: str) -> BookingCustomer:
        resp = await self._http.request(
            "GET",
            f"{ACUITY_API_BASE}/clients/{customer_id}",
            headers=await self._auth_headers(),
        )
        return mappers.to_booking_customer(resp.json())

    async def create_customer(self, customer: BookingCustomer) -> BookingCustomer:
        name_parts = (customer.name or "").split(" ", 1)
        body: dict[str, Any] = {
            "firstName": name_parts[0],
            "lastName": name_parts[1] if len(name_parts) > 1 else "",
        }
        if customer.email:
            body["email"] = customer.email
        if customer.phone:
            body["phone"] = customer.phone
        resp = await self._http.request(
            "POST",
            f"{ACUITY_API_BASE}/clients",
            headers=await self._auth_headers(),
            json=body,
        )
        return mappers.to_booking_customer(resp.json())
