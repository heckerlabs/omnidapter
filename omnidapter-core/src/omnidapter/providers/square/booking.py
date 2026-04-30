"""Square Appointments booking service implementation."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from datetime import datetime
from typing import Any

from omnidapter.auth.models import OAuth2Credentials
from omnidapter.providers.square import mappers
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

SQUARE_API_BASE = "https://connect.squareup.com/v2"
_SQUARE_VERSION = "2024-01-17"

_SQUARE_CAPABILITIES = frozenset(
    {
        BookingCapability.LIST_SERVICES,
        BookingCapability.GET_SERVICE,
        BookingCapability.LIST_STAFF,
        BookingCapability.GET_STAFF,
        BookingCapability.LIST_LOCATIONS,
        BookingCapability.GET_AVAILABILITY,
        BookingCapability.CREATE_BOOKING,
        BookingCapability.CANCEL_BOOKING,
        BookingCapability.RESCHEDULE_BOOKING,
        BookingCapability.UPDATE_BOOKING,
        BookingCapability.LIST_BOOKINGS,
        BookingCapability.GET_BOOKING,
        BookingCapability.CUSTOMER_LOOKUP,
        BookingCapability.CUSTOMER_MANAGEMENT,
        BookingCapability.MULTI_LOCATION,
        BookingCapability.MULTI_STAFF,
    }
)


class SquareBookingService(BookingService):
    """Square Appointments v2 API booking service."""

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
            provider_key="square",
            retry_policy=retry_policy,
            hooks=hooks,
            default_headers={"Square-Version": _SQUARE_VERSION},
        )

    @property
    def capabilities(self) -> frozenset[BookingCapability]:
        return _SQUARE_CAPABILITIES

    @property
    def _provider_key(self) -> str:
        return "square"

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
        params: dict[str, Any] = {"types": "ITEM"}
        if location_id:
            params["location_id"] = location_id
        resp = await self._http.request(
            "GET",
            f"{SQUARE_API_BASE}/catalog/list",
            headers=await self._auth_headers(),
            params=params,
        )
        objects = resp.json().get("objects") or []
        services: list[ServiceType] = []
        for obj in objects:
            if obj.get("type") != "ITEM":
                continue
            item_data = obj.get("item_data") or {}
            for variation in item_data.get("variations") or []:
                services.append(mappers.to_service_type(item_data, variation))
        return services

    async def get_service_type(self, service_id: str) -> ServiceType:
        self._require_capability(BookingCapability.GET_SERVICE)
        resp = await self._http.request(
            "GET",
            f"{SQUARE_API_BASE}/catalog/object/{service_id}",
            headers=await self._auth_headers(),
        )
        obj = resp.json().get("object") or {}
        # service_id is a variation ID; we need its parent item
        if obj.get("type") == "ITEM_VARIATION":
            vd = obj.get("item_variation_data") or {}
            # Re-fetch the parent item for name/description
            parent_id = vd.get("item_id")
            if parent_id:
                parent_resp = await self._http.request(
                    "GET",
                    f"{SQUARE_API_BASE}/catalog/object/{parent_id}",
                    headers=await self._auth_headers(),
                )
                parent = parent_resp.json().get("object") or {}
                return mappers.to_service_type(parent.get("item_data") or {}, obj)
            return mappers.to_service_type({}, obj)
        # It's an ITEM; return first variation
        item_data = obj.get("item_data") or {}
        variations = item_data.get("variations") or [{}]
        return mappers.to_service_type(item_data, variations[0])

    async def list_staff(
        self,
        service_id: str | None = None,
        location_id: str | None = None,
    ) -> list[StaffMember]:
        resp = await self._http.request(
            "GET",
            f"{SQUARE_API_BASE}/bookings/team-member-booking-profiles",
            headers=await self._auth_headers(),
        )
        profiles = resp.json().get("team_member_booking_profiles") or []
        return [mappers.to_staff_member(p) for p in profiles if p.get("is_bookable")]

    async def get_staff(self, staff_id: str) -> StaffMember:
        self._require_capability(BookingCapability.GET_STAFF)
        resp = await self._http.request(
            "GET",
            f"{SQUARE_API_BASE}/bookings/team-member-booking-profiles/{staff_id}",
            headers=await self._auth_headers(),
        )
        return mappers.to_staff_member(resp.json().get("team_member_booking_profile") or {})

    async def list_locations(self) -> list[BookingLocation]:
        resp = await self._http.request(
            "GET",
            f"{SQUARE_API_BASE}/locations",
            headers=await self._auth_headers(),
        )
        return [mappers.to_location(loc) for loc in resp.json().get("locations") or []]

    async def get_availability(
        self,
        service_id: str,
        start: datetime,
        end: datetime,
        staff_id: str | None = None,
        location_id: str | None = None,
        timezone: str | None = None,
    ) -> list[AvailabilitySlot]:
        segment_filter: dict[str, Any] = {"service_variation_id": service_id}
        if staff_id:
            segment_filter["team_member_id_filter"] = {"any": [staff_id]}

        body: dict[str, Any] = {
            "query": {
                "filter": {
                    "start_at_range": {
                        "start_at": start.isoformat(),
                        "end_at": end.isoformat(),
                    },
                    "segment_filters": [segment_filter],
                }
            }
        }
        if location_id:
            body["query"]["filter"]["location_id_filter"] = {"any": [location_id]}

        resp = await self._http.request(
            "POST",
            f"{SQUARE_API_BASE}/bookings/availability/search",
            headers=await self._auth_headers(),
            json=body,
        )
        return [
            mappers.to_availability_slot(avail, service_id)
            for avail in resp.json().get("availabilities") or []
        ]

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
        variation_version = (svc.provider_data or {}).get("service_variation_version") or 1

        segment: dict[str, Any] = {
            "service_variation_id": request.service_id,
            "service_variation_version": variation_version,
            "duration_minutes": svc.duration_minutes or 30,
        }
        if request.staff_id:
            segment["team_member_id"] = request.staff_id

        booking: dict[str, Any] = {
            "start_at": request.start.isoformat(),
            "appointment_segments": [segment],
        }
        if customer.id:
            booking["customer_id"] = customer.id
        if request.location_id:
            booking["location_id"] = request.location_id
        if request.notes:
            booking["customer_note"] = request.notes

        body = {
            "idempotency_key": str(uuid.uuid4()),
            "booking": booking,
        }
        resp = await self._http.request(
            "POST",
            f"{SQUARE_API_BASE}/bookings",
            headers=await self._auth_headers(),
            json=body,
        )
        return mappers.to_booking(resp.json().get("booking") or resp.json())

    async def get_booking(self, booking_id: str) -> Booking:
        self._require_capability(BookingCapability.GET_BOOKING)
        resp = await self._http.request(
            "GET",
            f"{SQUARE_API_BASE}/bookings/{booking_id}",
            headers=await self._auth_headers(),
        )
        return mappers.to_booking(resp.json().get("booking") or resp.json())

    def list_bookings(self, request: ListBookingsRequest) -> AsyncIterator[Booking]:
        return self._iter_bookings(request)

    async def _iter_bookings(self, request: ListBookingsRequest) -> AsyncGenerator[Booking, None]:
        params: dict[str, Any] = {}
        if request.start:
            params["start_at_min"] = request.start.isoformat()
        if request.end:
            params["start_at_max"] = request.end.isoformat()
        if request.staff_id:
            params["team_member_id"] = request.staff_id
        if request.location_id:
            params["location_id"] = request.location_id

        page_size = request.page_size or 100
        params["limit"] = page_size
        cursor: str | None = None
        headers = await self._auth_headers()
        while True:
            if cursor:
                params["cursor"] = cursor
            resp = await self._http.request(
                "GET",
                f"{SQUARE_API_BASE}/bookings",
                headers=headers,
                params=params,
            )
            data = resp.json()
            bookings = data.get("bookings") or []
            for item in bookings:
                yield mappers.to_booking(item)
            cursor = data.get("cursor")
            if not cursor or len(bookings) < page_size:
                break

    async def update_booking(self, request: UpdateBookingRequest) -> Booking:
        # Fetch current booking to build full update payload
        current_resp = await self._http.request(
            "GET",
            f"{SQUARE_API_BASE}/bookings/{request.booking_id}",
            headers=await self._auth_headers(),
        )
        current = current_resp.json().get("booking") or {}
        booking: dict[str, Any] = {
            "version": current.get("version", 0),
        }
        if request.start:
            booking["start_at"] = request.start.isoformat()
        if request.notes is not None:
            booking["customer_note"] = request.notes
        body = {
            "idempotency_key": str(uuid.uuid4()),
            "booking": booking,
        }
        resp = await self._http.request(
            "PUT",
            f"{SQUARE_API_BASE}/bookings/{request.booking_id}",
            headers=await self._auth_headers(),
            json=body,
        )
        return mappers.to_booking(resp.json().get("booking") or resp.json())

    async def cancel_booking(self, booking_id: str, reason: str | None = None) -> None:
        # Square cancel requires booking version
        current_resp = await self._http.request(
            "GET",
            f"{SQUARE_API_BASE}/bookings/{booking_id}",
            headers=await self._auth_headers(),
        )
        version = (current_resp.json().get("booking") or {}).get("version", 0)
        body = {
            "idempotency_key": str(uuid.uuid4()),
            "booking_version": version,
        }
        await self._http.request(
            "POST",
            f"{SQUARE_API_BASE}/bookings/{booking_id}/cancel",
            headers=await self._auth_headers(),
            json=body,
        )

    async def reschedule_booking(self, request: RescheduleBookingRequest) -> Booking:
        update_req = UpdateBookingRequest(
            booking_id=request.booking_id,
            start=request.new_start,
            staff_id=request.new_staff_id,
        )
        return await self.update_booking(update_req)

    async def find_customer(self, request: FindCustomerRequest) -> BookingCustomer | None:
        body: dict[str, Any] = {"query": {"filter": {}}}
        if request.email:
            body["query"]["filter"]["email_address"] = {"exact": request.email}
        elif request.phone:
            body["query"]["filter"]["phone_number"] = request.phone
        else:
            return None
        resp = await self._http.request(
            "POST",
            f"{SQUARE_API_BASE}/customers/search",
            headers=await self._auth_headers(),
            json=body,
        )
        customers = resp.json().get("customers") or []
        if customers:
            return mappers.to_booking_customer(customers[0])
        return None

    async def get_customer(self, customer_id: str) -> BookingCustomer:
        resp = await self._http.request(
            "GET",
            f"{SQUARE_API_BASE}/customers/{customer_id}",
            headers=await self._auth_headers(),
        )
        return mappers.to_booking_customer(resp.json().get("customer") or {})

    async def create_customer(self, customer: BookingCustomer) -> BookingCustomer:
        name_parts = (customer.name or "").split(" ", 1)
        body: dict[str, Any] = {
            "idempotency_key": str(uuid.uuid4()),
            "given_name": name_parts[0],
        }
        if len(name_parts) > 1:
            body["family_name"] = name_parts[1]
        if customer.email:
            body["email_address"] = customer.email
        if customer.phone:
            body["phone_number"] = customer.phone
        resp = await self._http.request(
            "POST",
            f"{SQUARE_API_BASE}/customers",
            headers=await self._auth_headers(),
            json=body,
        )
        return mappers.to_booking_customer(resp.json().get("customer") or {})
