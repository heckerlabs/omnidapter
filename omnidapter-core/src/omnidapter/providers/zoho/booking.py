"""Zoho Bookings service implementation."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator, AsyncIterator
from datetime import datetime, timedelta, timezone
from typing import Any

from omnidapter.auth.models import OAuth2Credentials
from omnidapter.services.booking.capabilities import BookingCapability
from omnidapter.services.booking.interface import BookingService
from omnidapter.services.booking.models import (
    AvailabilitySlot,
    Booking,
    BookingCustomer,
    BookingLocation,
    BookingStatus,
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

_ZOHO_BOOKINGS_BASE = "https://www.zohoapis.com/bookings/v1/json"

_ZOHO_BOOKING_CAPABILITIES = frozenset(
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
    }
)

# Zoho Bookings date format: "30-Apr-2026 14:30:00"
_DT_FMT = "%d-%b-%Y %H:%M:%S"
_DATE_FMT = "%d-%b-%Y"


def _fmt_dt(dt: datetime) -> str:
    return dt.strftime(_DT_FMT)


def _fmt_date(dt: datetime) -> str:
    return dt.strftime(_DATE_FMT)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in (_DT_FMT, _DATE_FMT, "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
        with contextlib.suppress(ValueError, TypeError):
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
    return None


def _status(raw: str | None) -> BookingStatus:
    mapping = {
        "scheduled": BookingStatus.CONFIRMED,
        "cancelled": BookingStatus.CANCELLED,
        "noshow": BookingStatus.NO_SHOW,
    }
    return mapping.get((raw or "").lower(), BookingStatus.CONFIRMED)


def _to_service(data: dict) -> ServiceType:
    return ServiceType(
        id=str(data.get("id", "")),
        name=data.get("name") or "",
        description=data.get("description") or None,
        duration_minutes=data.get("duration") or None,
        price=str(data["cost"]) if data.get("cost") is not None else None,
        provider_data=data,
    )


def _to_staff(data: dict) -> StaffMember:
    return StaffMember(
        id=str(data.get("id", "")),
        name=data.get("name") or "",
        email=data.get("email") or None,
        service_ids=[str(s) for s in (data.get("assigned_services") or [])],
        provider_data=data,
    )


def _to_customer(data: dict) -> BookingCustomer:
    # customer info in appointment responses varies by endpoint
    return BookingCustomer(
        id=data.get("customer_id") or data.get("customer_email") or None,
        name=data.get("customer_name") or (data.get("customer_details") or {}).get("name"),
        email=data.get("customer_email") or (data.get("customer_details") or {}).get("email"),
        phone=data.get("customer_contact_no")
        or (data.get("customer_details") or {}).get("phone_number"),
        provider_data=data,
    )


def _to_booking(data: dict) -> Booking:
    start = _parse_dt(data.get("appointment_start_time")) or datetime.now(tz=timezone.utc)
    duration = data.get("duration") or 60
    end = _parse_dt(data.get("appointment_end_time")) or (start + timedelta(minutes=duration))
    customer_data = dict(data)
    # fetchappointment embeds customer_details sub-dict
    if "customer_details" in data and isinstance(data["customer_details"], dict):
        customer_data.update(data["customer_details"])
    return Booking(
        id=str(data.get("booking_id", "")),
        service_id=str(data.get("service_id") or data.get("service_name") or ""),
        start=start,
        end=end,
        status=_status(data.get("status")),
        customer=_to_customer(customer_data),
        staff_id=str(data.get("staff_id") or data.get("staff_name") or "") or None,
        notes=data.get("notes") or None,
        management_urls={"manage": data["summary_url"]} if data.get("summary_url") else None,
        provider_data=data,
    )


class ZohoBookingService(BookingService):
    """Zoho Bookings v1 service."""

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
            provider_key="zoho", retry_policy=retry_policy, hooks=hooks
        )

    @property
    def capabilities(self) -> frozenset[BookingCapability]:
        return _ZOHO_BOOKING_CAPABILITIES

    @property
    def _provider_key(self) -> str:
        return "zoho"

    async def _resolve_stored_credential(self) -> StoredCredential:
        return self._stored

    async def _auth_headers(self) -> dict[str, str]:
        stored = await self._resolve_stored_credential()
        creds = stored.credentials
        assert isinstance(creds, OAuth2Credentials)
        return {"Authorization": f"Zoho-oauthtoken {creds.access_token}"}

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        resp = await self._http.request(
            "GET",
            f"{_ZOHO_BOOKINGS_BASE}/{path}",
            headers=await self._auth_headers(),
            params=params,
        )
        return resp.json()

    async def _post(self, path: str, data: dict[str, Any]) -> Any:
        resp = await self._http.request(
            "POST",
            f"{_ZOHO_BOOKINGS_BASE}/{path}",
            headers=await self._auth_headers(),
            json=data,
        )
        return resp.json()

    async def _workspace_id(self) -> str | None:
        """Return the configured workspace_id, or fetch the first available one."""
        config = self._stored.provider_config or {}
        if wid := config.get("workspace_id"):
            return str(wid)
        data = await self._get("workspaces")
        workspaces = (data.get("response") or {}).get("workspaces") or []
        return str(workspaces[0]["id"]) if workspaces else None

    # ── Services ──────────────────────────────────────────────────────────────

    async def list_services(self, location_id: str | None = None) -> list[ServiceType]:
        self._require_capability(BookingCapability.LIST_SERVICES)
        workspace_id = await self._workspace_id()
        params: dict[str, Any] = {}
        if workspace_id:
            params["workspace_id"] = workspace_id
        data = await self._get("services", params)
        services = (data.get("response") or {}).get("services") or []
        return [_to_service(s) for s in services]

    async def get_service_type(self, service_id: str) -> ServiceType:
        self._require_capability(BookingCapability.GET_SERVICE)
        workspace_id = await self._workspace_id()
        params: dict[str, Any] = {"service_id": service_id}
        if workspace_id:
            params["workspace_id"] = workspace_id
        data = await self._get("services", params)
        services = (data.get("response") or {}).get("services") or []
        if services:
            return _to_service(services[0])
        return ServiceType(id=service_id, name=service_id)

    # ── Staff ─────────────────────────────────────────────────────────────────

    async def list_staff(
        self,
        service_id: str | None = None,
        location_id: str | None = None,
    ) -> list[StaffMember]:
        self._require_capability(BookingCapability.LIST_STAFF)
        workspace_id = await self._workspace_id()
        params: dict[str, Any] = {}
        if workspace_id:
            params["workspace_id"] = workspace_id
        if service_id:
            params["service_id"] = service_id
        data = await self._get("staffs", params)
        staffs = (data.get("response") or {}).get("staffs") or []
        return [_to_staff(s) for s in staffs]

    async def get_staff(self, staff_id: str) -> StaffMember:
        self._require_capability(BookingCapability.GET_STAFF)
        workspace_id = await self._workspace_id()
        params: dict[str, Any] = {"staff_id": staff_id}
        if workspace_id:
            params["workspace_id"] = workspace_id
        data = await self._get("staffs", params)
        staffs = (data.get("response") or {}).get("staffs") or []
        if staffs:
            return _to_staff(staffs[0])
        return StaffMember(id=staff_id, name=staff_id)

    async def list_locations(self) -> list[BookingLocation]:
        self._require_capability(BookingCapability.LIST_LOCATIONS)
        return []  # unreachable

    # ── Availability ──────────────────────────────────────────────────────────

    async def get_availability(
        self,
        service_id: str,
        start: datetime,
        end: datetime,
        staff_id: str | None = None,
        location_id: str | None = None,
        timezone: str | None = None,
    ) -> list[AvailabilitySlot]:
        self._require_capability(BookingCapability.GET_AVAILABILITY)
        slots: list[AvailabilitySlot] = []
        current = start.date()
        end_date = end.date()
        while current <= end_date:
            params: dict[str, Any] = {
                "service_id": service_id,
                "selected_date": current.strftime(_DATE_FMT),
            }
            if staff_id:
                params["staff_id"] = staff_id
            if timezone:
                params["timezone"] = timezone
            data = await self._get("availableslots", params)
            time_strs: list[str] = (data.get("response") or {}).get("slots") or []
            tz = start.tzinfo
            for time_str in time_strs:
                with contextlib.suppress(ValueError):
                    hour, minute = (int(p) for p in time_str.split(":")[:2])
                    slot_start = datetime(
                        current.year, current.month, current.day, hour, minute, tzinfo=tz
                    )
                    if start <= slot_start < end:
                        # duration comes from service; default 60 min
                        slot_end = slot_start + timedelta(minutes=60)
                        slots.append(
                            AvailabilitySlot(
                                start=slot_start,
                                end=slot_end,
                                service_id=service_id,
                                staff_id=staff_id,
                            )
                        )
            current += timedelta(days=1)
        return slots

    # ── Bookings ──────────────────────────────────────────────────────────────

    async def create_booking(self, request: CreateBookingRequest) -> Booking:
        self._require_capability(BookingCapability.CREATE_BOOKING)
        customer = request.customer
        payload: dict[str, Any] = {
            "service_id": request.service_id,
            "from_time": _fmt_dt(request.start),
            "customer_details": {
                "name": customer.name or "",
                "email": customer.email or "",
                "phone_number": customer.phone or "",
            },
        }
        if request.staff_id:
            payload["staff_id"] = request.staff_id
        if request.notes:
            payload["notes"] = request.notes
        if customer.timezone:
            payload["timezone"] = customer.timezone
        data = await self._post("appointment", payload)
        booking_id = (data.get("response") or {}).get("booking_id") or ""
        return await self.get_booking(booking_id)

    async def get_booking(self, booking_id: str) -> Booking:
        self._require_capability(BookingCapability.GET_BOOKING)
        data = await self._get("getappointment", {"booking_id": booking_id})
        appt = data.get("response") or {}
        return _to_booking(appt)

    def list_bookings(self, request: ListBookingsRequest) -> AsyncIterator[Booking]:
        self._require_capability(BookingCapability.LIST_BOOKINGS)
        return self._iter_bookings(request)

    async def _iter_bookings(self, request: ListBookingsRequest) -> AsyncGenerator[Booking, None]:
        page = 1
        per_page = min(request.page_size or 100, 100)
        while True:
            payload: dict[str, Any] = {"page": page, "per_page": per_page}
            if request.start:
                payload["from_time"] = _fmt_dt(request.start)
            if request.end:
                payload["to_time"] = _fmt_dt(request.end)
            if request.staff_id:
                payload["staff_id"] = request.staff_id
            if request.service_id:
                payload["service_id"] = request.service_id
            if request.status:
                payload["status"] = request.status
            data = await self._post("fetchappointment", payload)
            response = data.get("response") or {}
            appointments = response.get("appointments") or []
            for appt in appointments:
                yield _to_booking(appt)
            if not response.get("next_page_available"):
                break
            page += 1

    async def cancel_booking(self, booking_id: str, reason: str | None = None) -> None:
        self._require_capability(BookingCapability.CANCEL_BOOKING)
        payload: dict[str, Any] = {"booking_id": booking_id, "action": "cancel"}
        if reason:
            payload["reason"] = reason
        await self._post("updateappointment", payload)

    async def update_booking(self, request: UpdateBookingRequest) -> Booking:
        self._require_capability(BookingCapability.UPDATE_BOOKING)
        payload: dict[str, Any] = {"booking_id": request.booking_id}
        if request.status:
            payload["action"] = request.status
        if request.notes is not None:
            payload["notes"] = request.notes
        data = await self._post("updateappointment", payload)
        appt = data.get("response") or {}
        return (
            _to_booking(appt)
            if appt.get("booking_id")
            else await self.get_booking(request.booking_id)
        )

    async def reschedule_booking(self, request: RescheduleBookingRequest) -> Booking:
        self._require_capability(BookingCapability.RESCHEDULE_BOOKING)
        payload: dict[str, Any] = {"booking_id": request.booking_id}
        if request.new_start:
            payload["start_time"] = _fmt_dt(request.new_start)
        if request.new_staff_id:
            payload["staff_id"] = request.new_staff_id
        data = await self._post("rescheduleappointment", payload)
        appt = data.get("response") or {}
        return (
            _to_booking(appt)
            if appt.get("booking_id")
            else await self.get_booking(request.booking_id)
        )

    # ── Customer lookup ───────────────────────────────────────────────────────

    async def find_customer(self, request: FindCustomerRequest) -> BookingCustomer | None:
        self._require_capability(BookingCapability.CUSTOMER_LOOKUP)
        payload: dict[str, Any] = {"per_page": 1, "page": 1}
        if request.email:
            payload["customer_email"] = request.email
        elif request.phone:
            payload["customer_phone_number"] = request.phone
        elif request.name:
            payload["customer_name"] = request.name
        else:
            return None
        data = await self._post("fetchappointment", payload)
        appointments = (data.get("response") or {}).get("appointments") or []
        if not appointments:
            return None
        appt = appointments[0]
        return _to_customer(appt)

    async def get_customer(self, customer_id: str) -> BookingCustomer:
        from omnidapter.core.errors import UnsupportedCapabilityError

        raise UnsupportedCapabilityError(
            "Zoho Bookings does not have a standalone customer endpoint. "
            "Use find_customer() to look up by email or phone.",
            provider_key="zoho",
            capability=BookingCapability.CUSTOMER_MANAGEMENT,
        )

    async def create_customer(self, customer: BookingCustomer) -> BookingCustomer:
        from omnidapter.core.errors import UnsupportedCapabilityError

        raise UnsupportedCapabilityError(
            "Zoho Bookings does not have a standalone customer creation endpoint. "
            "Customers are created implicitly when creating a booking.",
            provider_key="zoho",
            capability=BookingCapability.CUSTOMER_MANAGEMENT,
        )
