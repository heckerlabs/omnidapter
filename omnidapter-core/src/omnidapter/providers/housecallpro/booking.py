"""Housecall Pro booking service implementation."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator, AsyncIterator
from datetime import datetime, timedelta
from typing import Any

from omnidapter.auth.models import ApiKeyCredentials
from omnidapter.providers.housecallpro import mappers
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

HCP_API_BASE = "https://api.housecallpro.com"

_HCP_CAPABILITIES = frozenset(
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
        BookingCapability.CUSTOMER_LOOKUP,
        BookingCapability.CUSTOMER_MANAGEMENT,
        BookingCapability.MULTI_STAFF,
    }
)


class HousecallProBookingService(BookingService):
    """Housecall Pro v1 REST API booking service."""

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
            provider_key="housecallpro",
            retry_policy=retry_policy,
            hooks=hooks,
        )

    @property
    def capabilities(self) -> frozenset[BookingCapability]:
        return _HCP_CAPABILITIES

    @property
    def _provider_key(self) -> str:
        return "housecallpro"

    async def _resolve_stored_credential(self) -> StoredCredential:
        resolver = getattr(self, "_credential_resolver", None)
        if resolver is None:
            return self._stored
        self._stored = await resolver(self._connection_id)
        return self._stored

    async def _auth_headers(self) -> dict[str, str]:
        creds = (await self._resolve_stored_credential()).credentials
        if isinstance(creds, ApiKeyCredentials):
            return {"Authorization": f"Bearer {creds.api_key}"}
        return {}

    async def list_services(self, location_id: str | None = None) -> list[ServiceType]:
        # HCP doesn't have a dedicated service catalog; derive from recent line item names
        # Return a generic "Job" service type backed by provider_config if set
        config = (await self._resolve_stored_credential()).provider_config or {}
        services = config.get("services")
        if services:
            return [ServiceType(id=s, name=s) for s in services]
        return [ServiceType(id="job", name="Job", description="Housecall Pro job")]

    async def get_service_type(self, service_id: str) -> ServiceType:
        self._require_capability(BookingCapability.GET_SERVICE)
        services = await self.list_services()
        for svc in services:
            if svc.id == service_id:
                return svc
        return ServiceType(id=service_id, name="Job")

    async def list_staff(
        self,
        service_id: str | None = None,
        location_id: str | None = None,
    ) -> list[StaffMember]:
        resp = await self._http.request(
            "GET",
            f"{HCP_API_BASE}/api/v1/employees",
            headers=await self._auth_headers(),
        )
        data = resp.json()
        employees: list[Any] = (
            data.get("employees") or []
            if isinstance(data, dict)
            else (data if isinstance(data, list) else [])
        )
        return [mappers.to_staff_member(e) for e in employees]

    async def get_staff(self, staff_id: str) -> StaffMember:
        self._require_capability(BookingCapability.GET_STAFF)
        resp = await self._http.request(
            "GET",
            f"{HCP_API_BASE}/api/v1/employees/{staff_id}",
            headers=await self._auth_headers(),
        )
        return mappers.to_staff_member(resp.json())

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
        # Fetch existing jobs in range to subtract from working hours
        params: dict[str, Any] = {
            "scheduled_start_min": start.isoformat(),
            "scheduled_end_max": end.isoformat(),
            "page_size": 200,
        }
        if staff_id:
            params["employee_id"] = staff_id
        resp = await self._http.request(
            "GET",
            f"{HCP_API_BASE}/api/v1/jobs",
            headers=await self._auth_headers(),
            params=params,
        )
        data = resp.json()
        jobs: list[Any] = (
            data.get("jobs") or []
            if isinstance(data, dict)
            else (data if isinstance(data, list) else [])
        )

        booked_ranges: list[tuple[datetime, datetime]] = []
        for job in jobs:
            schedule = job.get("schedule") or {}
            s_str = schedule.get("scheduled_start") or ""
            e_str = schedule.get("scheduled_end") or ""
            if s_str and e_str:
                with contextlib.suppress(ValueError):
                    booked_ranges.append((mappers.parse_dt(s_str), mappers.parse_dt(e_str)))

        slot_duration = timedelta(hours=1)
        slots: list[AvailabilitySlot] = []
        current_day = start.date()
        end_day = end.date()
        while current_day <= end_day:
            day_start = datetime(
                current_day.year, current_day.month, current_day.day, 9, 0, tzinfo=start.tzinfo
            )
            day_end = datetime(
                current_day.year, current_day.month, current_day.day, 17, 0, tzinfo=start.tzinfo
            )
            slot_s = max(day_start, start)
            while slot_s + slot_duration <= min(day_end, end):
                slot_e = slot_s + slot_duration
                overlaps = any(
                    not (slot_e <= b_start or slot_s >= b_end) for b_start, b_end in booked_ranges
                )
                if not overlaps:
                    slots.append(mappers.to_availability_slot(slot_s, slot_e, service_id, staff_id))
                slot_s += slot_duration
            current_day = current_day + timedelta(days=1)
        return slots

    async def _resolve_customer(self, customer: BookingCustomer) -> BookingCustomer:
        if customer.id:
            return customer
        if customer.email:
            found = await self.find_customer(FindCustomerRequest(email=customer.email))
            if found:
                return found
        return await self.create_customer(customer)

    async def create_booking(self, request: CreateBookingRequest) -> Booking:
        customer = await self._resolve_customer(request.customer)
        body: dict[str, Any] = {
            "customer_id": customer.id,
            "schedule": {
                "scheduled_start": request.start.isoformat(),
            },
        }
        if request.notes:
            body["description"] = request.notes
        if request.staff_id:
            body["assigned_employee_ids"] = [request.staff_id]
        if request.service_id and request.service_id != "job":
            body["line_items"] = [{"name": request.service_id, "quantity": 1}]
        resp = await self._http.request(
            "POST",
            f"{HCP_API_BASE}/api/v1/jobs",
            headers=await self._auth_headers(),
            json=body,
        )
        return mappers.to_booking(resp.json())

    async def get_booking(self, booking_id: str) -> Booking:
        self._require_capability(BookingCapability.GET_BOOKING)
        resp = await self._http.request(
            "GET",
            f"{HCP_API_BASE}/api/v1/jobs/{booking_id}",
            headers=await self._auth_headers(),
        )
        return mappers.to_booking(resp.json())

    def list_bookings(self, request: ListBookingsRequest) -> AsyncIterator[Booking]:
        return self._iter_bookings(request)

    async def _iter_bookings(self, request: ListBookingsRequest) -> AsyncGenerator[Booking, None]:
        params: dict[str, Any] = {}
        if request.start:
            params["scheduled_start_min"] = request.start.isoformat()
        if request.end:
            params["scheduled_end_max"] = request.end.isoformat()
        if request.staff_id:
            params["employee_id"] = request.staff_id

        page_size = request.page_size or 100
        params["page_size"] = page_size
        page = 1
        headers = await self._auth_headers()
        while True:
            params["page"] = page
            resp = await self._http.request(
                "GET",
                f"{HCP_API_BASE}/api/v1/jobs",
                headers=headers,
                params=params,
            )
            data = resp.json()
            jobs: list[Any] = (
                data.get("jobs") or []
                if isinstance(data, dict)
                else (data if isinstance(data, list) else [])
            )
            if not jobs:
                break
            for job in jobs:
                yield mappers.to_booking(job)
            if len(jobs) < page_size:
                break
            page += 1

    async def update_booking(self, request: UpdateBookingRequest) -> Booking:
        body: dict[str, Any] = {}
        if request.start:
            body["schedule"] = {"scheduled_start": request.start.isoformat()}
        if request.notes is not None:
            body["description"] = request.notes
        resp = await self._http.request(
            "PATCH",
            f"{HCP_API_BASE}/api/v1/jobs/{request.booking_id}",
            headers=await self._auth_headers(),
            json=body,
        )
        return mappers.to_booking(resp.json())

    async def cancel_booking(self, booking_id: str, reason: str | None = None) -> None:
        await self._http.request(
            "DELETE",
            f"{HCP_API_BASE}/api/v1/jobs/{booking_id}",
            headers=await self._auth_headers(),
        )

    async def reschedule_booking(self, request: RescheduleBookingRequest) -> Booking:
        update_req = UpdateBookingRequest(
            booking_id=request.booking_id,
            start=request.new_start,
            staff_id=request.new_staff_id,
        )
        return await self.update_booking(update_req)

    async def find_customer(self, request: FindCustomerRequest) -> BookingCustomer | None:
        params: dict[str, Any] = {}
        if request.email:
            params["email"] = request.email
        elif request.name:
            params["q"] = request.name
        else:
            return None
        resp = await self._http.request(
            "GET",
            f"{HCP_API_BASE}/api/v1/customers",
            headers=await self._auth_headers(),
            params=params,
        )
        data = resp.json()
        customers: list[Any] = (
            data.get("customers") or []
            if isinstance(data, dict)
            else (data if isinstance(data, list) else [])
        )
        if customers:
            return mappers.to_booking_customer(customers[0])
        return None

    async def get_customer(self, customer_id: str) -> BookingCustomer:
        resp = await self._http.request(
            "GET",
            f"{HCP_API_BASE}/api/v1/customers/{customer_id}",
            headers=await self._auth_headers(),
        )
        return mappers.to_booking_customer(resp.json())

    async def create_customer(self, customer: BookingCustomer) -> BookingCustomer:
        name_parts = (customer.name or "").split(" ", 1)
        body: dict[str, Any] = {
            "first_name": name_parts[0],
            "last_name": name_parts[1] if len(name_parts) > 1 else "",
        }
        if customer.email:
            body["email"] = customer.email
        if customer.phone:
            body["mobile_number"] = customer.phone
        resp = await self._http.request(
            "POST",
            f"{HCP_API_BASE}/api/v1/customers",
            headers=await self._auth_headers(),
            json=body,
        )
        return mappers.to_booking_customer(resp.json())
