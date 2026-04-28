"""Microsoft Bookings (Graph API) booking service implementation."""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from datetime import datetime, timedelta
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

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

_MS_BOOKING_CAPABILITIES = frozenset(
    {
        BookingCapability.LIST_SERVICES,
        BookingCapability.LIST_STAFF,
        BookingCapability.LIST_LOCATIONS,
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


def _ms_dt(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def _ms_dt_body(dt: datetime) -> dict[str, str]:
    return {"dateTime": dt.isoformat(), "timeZone": "UTC"}


def _status(raw: str) -> BookingStatus:
    s = raw.lower()
    if s in ("cancelled", "noshow"):
        return BookingStatus.CANCELLED if s == "cancelled" else BookingStatus.NO_SHOW
    if s == "pending":
        return BookingStatus.PENDING
    return BookingStatus.CONFIRMED


def _to_service_type(data: dict) -> ServiceType:
    duration_str = data.get("defaultDuration") or "PT1H"
    # Parse ISO 8601 duration (e.g. PT30M, PT1H)
    import re

    minutes = 0
    if m := re.search(r"(\d+)H", duration_str):
        minutes += int(m.group(1)) * 60
    if m := re.search(r"(\d+)M", duration_str):
        minutes += int(m.group(1))
    price = data.get("defaultPrice")
    return ServiceType(
        id=str(data.get("id", "")),
        name=data.get("displayName") or data.get("name", ""),
        description=data.get("description") or None,
        duration_minutes=minutes or None,
        price=str(price) if price else None,
        provider_data=data,
    )


def _to_staff_member(data: dict) -> StaffMember:
    return StaffMember(
        id=str(data.get("id", "")),
        name=data.get("displayName", ""),
        email=data.get("emailAddress") or None,
        service_ids=[],
        provider_data=data,
    )


def _to_location(data: dict) -> BookingLocation:
    addr = data.get("address") or {}
    parts = filter(
        None,
        [
            addr.get("street"),
            addr.get("city"),
            addr.get("state"),
            addr.get("postalCode"),
        ],
    )
    return BookingLocation(
        id=str(data.get("id", "")),
        name=data.get("displayName", ""),
        address=", ".join(parts) or None,
        provider_data=data,
    )


def _to_booking(data: dict) -> Booking:
    customers = data.get("customers") or [{}]
    primary = customers[0] if customers else {}
    customer = BookingCustomer(
        id=primary.get("customerId"),
        name=primary.get("customerName") or None,
        email=primary.get("customerEmailAddress") or None,
        phone=primary.get("customerPhone") or None,
        timezone=primary.get("timeZone") or None,
    )
    start_dt = data.get("startDateTime") or {}
    end_dt = data.get("endDateTime") or {}
    start_str = start_dt.get("dateTime", "")
    end_str = end_dt.get("dateTime", "")
    start = _ms_dt(start_str) if start_str else datetime.now()
    end = _ms_dt(end_str) if end_str else start + timedelta(hours=1)

    # staff member from staffMemberIds
    staff_ids = data.get("staffMemberIds") or []
    staff_id = staff_ids[0] if staff_ids else None

    # management URLs
    urls: dict[str, str] = {}
    if data.get("selfServiceAppointmentId"):
        urls["manage"] = data["selfServiceAppointmentId"]

    return Booking(
        id=str(data.get("id", "")),
        service_id=str(data.get("serviceId", "")),
        start=start,
        end=end,
        status=_status(data.get("status", "booked")),
        customer=customer,
        staff_id=str(staff_id) if staff_id else None,
        location_id=data.get("locationId"),
        notes=data.get("additionalInformation") or None,
        management_urls=urls or None,
        provider_data=data,
    )


def _to_booking_customer(data: dict) -> BookingCustomer:
    return BookingCustomer(
        id=str(data.get("id", "")),
        name=data.get("displayName") or None,
        email=data.get("emailAddress") or None,
        phone=data.get("phone") or None,
        provider_data=data,
    )


class MicrosoftBookingService(BookingService):
    """Microsoft Bookings via Graph API."""

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
            provider_key="microsoft",
            retry_policy=retry_policy,
            hooks=hooks,
        )

    @property
    def capabilities(self) -> frozenset[BookingCapability]:
        return _MS_BOOKING_CAPABILITIES

    @property
    def _provider_key(self) -> str:
        return "microsoft"

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

    def _business_base(self, stored: StoredCredential) -> str:
        config = stored.provider_config or {}
        business_id = config.get("business_id", "")
        return f"{GRAPH_BASE}/solutions/bookingBusinesses/{business_id}"

    async def _base(self) -> str:
        return self._business_base(await self._resolve_stored_credential())

    async def list_services(self, location_id: str | None = None) -> list[ServiceType]:
        base = await self._base()
        resp = await self._http.request(
            "GET",
            f"{base}/services",
            headers=await self._auth_headers(),
        )
        return [_to_service_type(s) for s in resp.json().get("value") or []]

    async def get_service_type(self, service_id: str) -> ServiceType:
        base = await self._base()
        resp = await self._http.request(
            "GET",
            f"{base}/services/{service_id}",
            headers=await self._auth_headers(),
        )
        return _to_service_type(resp.json())

    async def list_staff(
        self,
        service_id: str | None = None,
        location_id: str | None = None,
    ) -> list[StaffMember]:
        base = await self._base()
        resp = await self._http.request(
            "GET",
            f"{base}/staffMembers",
            headers=await self._auth_headers(),
        )
        return [_to_staff_member(s) for s in resp.json().get("value") or []]

    async def get_staff(self, staff_id: str) -> StaffMember:
        base = await self._base()
        resp = await self._http.request(
            "GET",
            f"{base}/staffMembers/{staff_id}",
            headers=await self._auth_headers(),
        )
        return _to_staff_member(resp.json())

    async def list_locations(self) -> list[BookingLocation]:
        # Microsoft Bookings businesses have a single primary location
        stored = await self._resolve_stored_credential()
        base = self._business_base(stored)
        resp = await self._http.request(
            "GET",
            base,
            headers=await self._auth_headers(),
        )
        data = resp.json()
        addr = data.get("address") or {}
        parts = filter(
            None,
            [
                addr.get("street"),
                addr.get("city"),
                addr.get("state"),
                addr.get("postalCode"),
            ],
        )
        return [
            BookingLocation(
                id=str(data.get("id", "")),
                name=data.get("displayName", ""),
                address=", ".join(parts) or None,
                provider_data=data,
            )
        ]

    async def get_availability(
        self,
        service_id: str,
        start: datetime,
        end: datetime,
        staff_id: str | None = None,
        location_id: str | None = None,
        timezone: str | None = None,
    ) -> list[AvailabilitySlot]:
        base = await self._base()
        svc = await self.get_service_type(service_id)
        duration_minutes = svc.duration_minutes or 60

        # Get all staff if no specific staff_id
        if staff_id:
            staff_ids = [staff_id]
        else:
            staff = await self.list_staff(service_id=service_id)
            staff_ids = [s.id for s in staff[:10]]  # limit to avoid large payloads

        body: dict[str, Any] = {
            "startDateTime": _ms_dt_body(start),
            "endDateTime": _ms_dt_body(end),
            "staffIds": staff_ids,
        }
        resp = await self._http.request(
            "POST",
            f"{base}/getStaffAvailability",
            headers=await self._auth_headers(),
            json=body,
        )
        data = resp.json()
        items = data.get("staffAvailabilityItems") or []

        slots: list[AvailabilitySlot] = []
        slot_delta = timedelta(minutes=duration_minutes)
        for item in items:
            sid = item.get("staffId")
            for av in item.get("availabilityItems") or []:
                if av.get("status", "").lower() != "available":
                    continue
                av_start_dt = av.get("startDateTime") or {}
                av_end_dt = av.get("endDateTime") or {}
                av_start_str = av_start_dt.get("dateTime", "")
                av_end_str = av_end_dt.get("dateTime", "")
                if not av_start_str or not av_end_str:
                    continue
                av_start = _ms_dt(av_start_str)
                av_end = _ms_dt(av_end_str)
                # Slice the availability window into duration-length slots
                slot_s = av_start
                while slot_s + slot_delta <= av_end:
                    slots.append(
                        AvailabilitySlot(
                            start=slot_s,
                            end=slot_s + slot_delta,
                            service_id=service_id,
                            staff_id=str(sid) if sid else None,
                        )
                    )
                    slot_s += slot_delta
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
        svc = await self.get_service_type(request.service_id)
        duration_minutes = svc.duration_minutes or 60
        end = request.start + timedelta(minutes=duration_minutes)

        customer_payload: dict[str, Any] = {}
        if customer.id:
            customer_payload["customerId"] = customer.id
        if customer.name:
            customer_payload["customerName"] = customer.name
        if customer.email:
            customer_payload["customerEmailAddress"] = customer.email
        if customer.phone:
            customer_payload["customerPhone"] = customer.phone

        body: dict[str, Any] = {
            "serviceId": request.service_id,
            "startDateTime": _ms_dt_body(request.start),
            "endDateTime": _ms_dt_body(end),
            "customers": [customer_payload],
        }
        if request.staff_id:
            body["staffMemberIds"] = [request.staff_id]
        if request.notes:
            body["additionalInformation"] = request.notes

        base = await self._base()
        resp = await self._http.request(
            "POST",
            f"{base}/appointments",
            headers=await self._auth_headers(),
            json=body,
        )
        return _to_booking(resp.json())

    async def get_booking(self, booking_id: str) -> Booking:
        base = await self._base()
        resp = await self._http.request(
            "GET",
            f"{base}/appointments/{booking_id}",
            headers=await self._auth_headers(),
        )
        return _to_booking(resp.json())

    def list_bookings(self, request: ListBookingsRequest) -> AsyncIterator[Booking]:
        return self._iter_bookings(request)

    async def _iter_bookings(self, request: ListBookingsRequest) -> AsyncGenerator[Booking, None]:
        base = await self._base()
        params: dict[str, Any] = {}
        if request.start:
            params["$filter"] = f"startDateTime/dateTime ge '{request.start.isoformat()}'"
        if request.end and "$filter" in params:
            params["$filter"] += f" and endDateTime/dateTime le '{request.end.isoformat()}'"

        headers = await self._auth_headers()
        next_link: str | None = f"{base}/appointments"
        while next_link:
            resp = await self._http.request(
                "GET",
                next_link,
                headers=headers,
                params=params,
            )
            params = {}  # params only on first request; Graph handles @odata.nextLink
            data = resp.json()
            for item in data.get("value") or []:
                yield _to_booking(item)
            next_link = data.get("@odata.nextLink")

    async def update_booking(self, request: UpdateBookingRequest) -> Booking:
        base = await self._base()
        body: dict[str, Any] = {}
        if request.start:
            body["startDateTime"] = _ms_dt_body(request.start)
        if request.notes is not None:
            body["additionalInformation"] = request.notes
        if request.staff_id:
            body["staffMemberIds"] = [request.staff_id]
        resp = await self._http.request(
            "PATCH",
            f"{base}/appointments/{request.booking_id}",
            headers=await self._auth_headers(),
            json=body,
        )
        return _to_booking(resp.json())

    async def cancel_booking(self, booking_id: str, reason: str | None = None) -> None:
        base = await self._base()
        if reason:
            body: dict[str, Any] = {"cancellationMessage": reason}
            await self._http.request(
                "POST",
                f"{base}/appointments/{booking_id}/cancel",
                headers=await self._auth_headers(),
                json=body,
            )
        else:
            await self._http.request(
                "DELETE",
                f"{base}/appointments/{booking_id}",
                headers=await self._auth_headers(),
            )

    async def reschedule_booking(self, request: RescheduleBookingRequest) -> Booking:
        current = await self.get_booking(request.booking_id)
        update_req = UpdateBookingRequest(
            booking_id=request.booking_id,
            start=request.new_start,
            staff_id=request.new_staff_id,
        )
        updated = await self.update_booking(update_req)
        # If end wasn't set by update, adjust manually
        if updated.end == current.end and updated.start != current.start:
            # Re-fetch to get server-computed end
            return await self.get_booking(request.booking_id)
        return updated

    async def find_customer(self, request: FindCustomerRequest) -> BookingCustomer | None:
        base = await self._base()
        resp = await self._http.request(
            "GET",
            f"{base}/customers",
            headers=await self._auth_headers(),
        )
        customers = resp.json().get("value") or []
        for c in customers:
            if request.email and c.get("emailAddress", "").lower() == request.email.lower():
                return _to_booking_customer(c)
            if request.name and c.get("displayName", "").lower() == request.name.lower():
                return _to_booking_customer(c)
        return None

    async def get_customer(self, customer_id: str) -> BookingCustomer:
        base = await self._base()
        resp = await self._http.request(
            "GET",
            f"{base}/customers/{customer_id}",
            headers=await self._auth_headers(),
        )
        return _to_booking_customer(resp.json())

    async def create_customer(self, customer: BookingCustomer) -> BookingCustomer:
        base = await self._base()
        body: dict[str, Any] = {
            "displayName": customer.name or "",
        }
        if customer.email:
            body["emailAddress"] = customer.email
        if customer.phone:
            body["phone"] = customer.phone
        resp = await self._http.request(
            "POST",
            f"{base}/customers",
            headers=await self._auth_headers(),
            json=body,
        )
        return _to_booking_customer(resp.json())
