"""Cal.com booking service implementation."""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from datetime import datetime
from typing import Any

from omnidapter.auth.models import OAuth2Credentials
from omnidapter.providers.calcom import mappers
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

CALCOM_API_BASE = "https://api.cal.com/v2"
_CAL_VERSION_HEADER = "2024-08-13"

_CALCOM_CAPABILITIES = frozenset(
    {
        BookingCapability.LIST_SERVICES,
        BookingCapability.GET_SERVICE,
        BookingCapability.LIST_STAFF,
        BookingCapability.GET_STAFF,
        BookingCapability.GET_AVAILABILITY,
        BookingCapability.CREATE_BOOKING,
        BookingCapability.CANCEL_BOOKING,
        BookingCapability.RESCHEDULE_BOOKING,
        BookingCapability.UPDATE_BOOKING,
        BookingCapability.LIST_BOOKINGS,
        BookingCapability.GET_BOOKING,
        BookingCapability.MULTI_LOCATION,
        BookingCapability.MULTI_STAFF,
        BookingCapability.MULTI_SERVICE,
    }
)


class CalcomBookingService(BookingService):
    """Cal.com v2 API booking service."""

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
            provider_key="calcom",
            retry_policy=retry_policy,
            hooks=hooks,
            default_headers={"cal-api-version": _CAL_VERSION_HEADER},
        )

    @property
    def capabilities(self) -> frozenset[BookingCapability]:
        return _CALCOM_CAPABILITIES

    @property
    def _provider_key(self) -> str:
        return "calcom"

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

    def _data(self, resp: Any) -> Any:
        return resp.json().get("data", resp.json())

    async def list_services(self, location_id: str | None = None) -> list[ServiceType]:
        resp = await self._http.request(
            "GET",
            f"{CALCOM_API_BASE}/event-types",
            headers=await self._auth_headers(),
        )
        items = self._data(resp)
        if isinstance(items, dict):
            items = items.get("eventTypeGroups") or items.get("eventTypes") or []
            if items and isinstance(items[0], dict) and "eventTypes" in items[0]:
                event_types = []
                for group in items:
                    event_types.extend(group.get("eventTypes") or [])
                items = event_types
        return [mappers.to_service_type(item) for item in (items or [])]

    async def get_service_type(self, service_id: str) -> ServiceType:
        self._require_capability(BookingCapability.GET_SERVICE)
        resp = await self._http.request(
            "GET",
            f"{CALCOM_API_BASE}/event-types/{service_id}",
            headers=await self._auth_headers(),
        )
        return mappers.to_service_type(self._data(resp))

    async def list_staff(
        self,
        service_id: str | None = None,
        location_id: str | None = None,
    ) -> list[StaffMember]:
        resp = await self._http.request(
            "GET",
            f"{CALCOM_API_BASE}/memberships",
            headers=await self._auth_headers(),
        )
        items = self._data(resp)
        return [mappers.to_staff_member(item) for item in (items or [])]

    async def get_staff(self, staff_id: str) -> StaffMember:
        self._require_capability(BookingCapability.GET_STAFF)
        resp = await self._http.request(
            "GET",
            f"{CALCOM_API_BASE}/users/{staff_id}",
            headers=await self._auth_headers(),
        )
        return mappers.to_staff_member(self._data(resp))

    async def list_locations(self) -> list[BookingLocation]:
        # Cal.com locations are per-event-type; no standalone endpoint
        return []

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
        duration_minutes = svc.duration_minutes or 30

        params: dict[str, Any] = {
            "eventTypeId": service_id,
            "startTime": start.isoformat(),
            "endTime": end.isoformat(),
        }
        if timezone:
            params["timeZone"] = timezone
        resp = await self._http.request(
            "GET",
            f"{CALCOM_API_BASE}/slots/available",
            headers=await self._auth_headers(),
            params=params,
        )
        data = self._data(resp)
        slots_by_date = data.get("slots") or {}
        slots: list[AvailabilitySlot] = []
        for _date, times in slots_by_date.items():
            for time_item in times:
                time_str = time_item.get("time") if isinstance(time_item, dict) else time_item
                if time_str:
                    slots.append(
                        mappers.to_availability_slot(
                            time_str, service_id, duration_minutes, staff_id
                        )
                    )
        return slots

    async def create_booking(self, request: CreateBookingRequest) -> Booking:
        customer = request.customer
        body: dict[str, Any] = {
            "start": request.start.isoformat(),
            "eventTypeId": int(request.service_id),
            "attendee": {
                "name": customer.name or "",
                "email": customer.email or "",
                "timeZone": customer.timezone or "UTC",
            },
        }
        if request.notes:
            body["notes"] = request.notes
        if request.provider_data:
            body.update(request.provider_data)
        resp = await self._http.request(
            "POST",
            f"{CALCOM_API_BASE}/bookings",
            headers=await self._auth_headers(),
            json=body,
        )
        return mappers.to_booking(self._data(resp))

    async def get_booking(self, booking_id: str) -> Booking:
        self._require_capability(BookingCapability.GET_BOOKING)
        resp = await self._http.request(
            "GET",
            f"{CALCOM_API_BASE}/bookings/{booking_id}",
            headers=await self._auth_headers(),
        )
        return mappers.to_booking(self._data(resp))

    def list_bookings(self, request: ListBookingsRequest) -> AsyncIterator[Booking]:
        return self._iter_bookings(request)

    async def _iter_bookings(self, request: ListBookingsRequest) -> AsyncGenerator[Booking, None]:
        params: dict[str, Any] = {}
        if request.status:
            params["status"] = request.status.value
        if request.start:
            params["afterStart"] = request.start.isoformat()
        if request.end:
            params["beforeEnd"] = request.end.isoformat()

        page_size = request.page_size or 100
        params["limit"] = page_size
        cursor = 0
        headers = await self._auth_headers()
        while True:
            params["cursor"] = cursor
            resp = await self._http.request(
                "GET",
                f"{CALCOM_API_BASE}/bookings",
                headers=headers,
                params=params,
            )
            data = self._data(resp)
            bookings: list[Any] = (
                data.get("bookings") or []
                if isinstance(data, dict)
                else (data if isinstance(data, list) else [])
            )
            if not bookings:
                break
            for item in bookings:
                yield mappers.to_booking(item)
            if len(bookings) < page_size:
                break
            cursor += page_size

    async def update_booking(self, request: UpdateBookingRequest) -> Booking:
        body: dict[str, Any] = {}
        if request.start:
            body["start"] = request.start.isoformat()
        if request.notes is not None:
            body["notes"] = request.notes
        resp = await self._http.request(
            "PATCH",
            f"{CALCOM_API_BASE}/bookings/{request.booking_id}",
            headers=await self._auth_headers(),
            json=body,
        )
        return mappers.to_booking(self._data(resp))

    async def cancel_booking(self, booking_id: str, reason: str | None = None) -> None:
        body: dict[str, Any] = {}
        if reason:
            body["cancellationReason"] = reason
        await self._http.request(
            "POST",
            f"{CALCOM_API_BASE}/bookings/{booking_id}/cancel",
            headers=await self._auth_headers(),
            json=body,
        )

    async def reschedule_booking(self, request: RescheduleBookingRequest) -> Booking:
        body: dict[str, Any] = {"rescheduledTo": request.new_start.isoformat()}
        resp = await self._http.request(
            "POST",
            f"{CALCOM_API_BASE}/bookings/{request.booking_id}/reschedule",
            headers=await self._auth_headers(),
            json=body,
        )
        return mappers.to_booking(self._data(resp))

    async def find_customer(self, request: FindCustomerRequest) -> BookingCustomer | None:
        self._require_capability(BookingCapability.CUSTOMER_LOOKUP)
        return None  # unreachable

    async def get_customer(self, customer_id: str) -> BookingCustomer:
        self._require_capability(BookingCapability.CUSTOMER_MANAGEMENT)
        raise Exception("unreachable")

    async def create_customer(self, customer: BookingCustomer) -> BookingCustomer:
        self._require_capability(BookingCapability.CUSTOMER_MANAGEMENT)
        raise Exception("unreachable")
