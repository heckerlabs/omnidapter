"""Calendly booking service implementation."""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from datetime import datetime
from typing import Any

from omnidapter.auth.models import OAuth2Credentials
from omnidapter.providers.calendly import mappers
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

CALENDLY_API_BASE = "https://api.calendly.com"

_CALENDLY_CAPABILITIES = frozenset(
    {
        BookingCapability.LIST_SERVICES,
        BookingCapability.GET_SERVICE,
        BookingCapability.LIST_STAFF,
        BookingCapability.GET_STAFF,
        BookingCapability.GET_AVAILABILITY,
        BookingCapability.LIST_BOOKINGS,
        BookingCapability.GET_BOOKING,
        BookingCapability.CANCEL_BOOKING,
    }
)


class CalendlyBookingService(BookingService):
    """Calendly v2 API booking service."""

    def __init__(
        self,
        connection_id: str,
        stored_credential: StoredCredential,
        retry_policy: RetryPolicy | None = None,
        hooks: Any = None,
    ) -> None:
        self._connection_id = connection_id
        self._stored = stored_credential
        self._user_uri: str | None = None
        self._org_uri: str | None = None
        self._http = OmnidapterHttpClient(
            provider_key="calendly",
            retry_policy=retry_policy,
            hooks=hooks,
        )

    @property
    def capabilities(self) -> frozenset[BookingCapability]:
        return _CALENDLY_CAPABILITIES

    @property
    def _provider_key(self) -> str:
        return "calendly"

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

    async def _get_user_uri(self) -> str:
        if self._user_uri:
            return self._user_uri
        resp = await self._http.request(
            "GET",
            f"{CALENDLY_API_BASE}/users/me",
            headers=await self._auth_headers(),
        )
        data = resp.json()
        resource: dict[str, Any] = data.get("resource") or {}
        self._user_uri = str(resource.get("uri") or "")
        self._org_uri = str(resource.get("current_organization") or "")
        return self._user_uri

    async def list_services(self, location_id: str | None = None) -> list[ServiceType]:
        user_uri = await self._get_user_uri()
        resp = await self._http.request(
            "GET",
            f"{CALENDLY_API_BASE}/event_types",
            headers=await self._auth_headers(),
            params={"user": user_uri, "active": "true"},
        )
        return [mappers.to_service_type(item) for item in resp.json().get("collection") or []]

    async def get_service_type(self, service_id: str) -> ServiceType:
        self._require_capability(BookingCapability.GET_SERVICE)
        resp = await self._http.request(
            "GET",
            f"{CALENDLY_API_BASE}/event_types/{service_id}",
            headers=await self._auth_headers(),
        )
        return mappers.to_service_type(resp.json().get("resource") or {})

    async def list_staff(
        self,
        service_id: str | None = None,
        location_id: str | None = None,
    ) -> list[StaffMember]:
        await self._get_user_uri()
        org_uri = self._org_uri or ""
        resp = await self._http.request(
            "GET",
            f"{CALENDLY_API_BASE}/organization_memberships",
            headers=await self._auth_headers(),
            params={"organization": org_uri},
        )
        return [mappers.to_staff_member(item) for item in resp.json().get("collection") or []]

    async def get_staff(self, staff_id: str) -> StaffMember:
        self._require_capability(BookingCapability.GET_STAFF)
        resp = await self._http.request(
            "GET",
            f"{CALENDLY_API_BASE}/users/{staff_id}",
            headers=await self._auth_headers(),
        )
        resource = resp.json().get("resource") or {}
        return mappers.to_staff_member(resource)

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
        duration_minutes = svc.duration_minutes or 30
        # service_id is the UUID; Calendly needs the full URI
        event_type_uri = (svc.provider_data or {}).get(
            "uri"
        ) or f"{CALENDLY_API_BASE}/event_types/{service_id}"

        params: dict[str, Any] = {
            "event_type": event_type_uri,
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
        }
        if timezone:
            params["timezone"] = timezone
        resp = await self._http.request(
            "GET",
            f"{CALENDLY_API_BASE}/event_type_available_times",
            headers=await self._auth_headers(),
            params=params,
        )
        return [
            mappers.to_availability_slot(item, service_id, duration_minutes)
            for item in resp.json().get("collection") or []
            if item.get("invitees_remaining", 1) > 0
        ]

    async def create_booking(self, request: CreateBookingRequest) -> Booking:
        self._require_capability(BookingCapability.CREATE_BOOKING)
        return Booking(  # unreachable — capability not in set
            id="",
            service_id="",
            start=request.start,
            end=request.start,
            status=__import__(
                "omnidapter.services.booking.models", fromlist=["BookingStatus"]
            ).BookingStatus.PENDING,
            customer=request.customer,
        )

    async def get_booking(self, booking_id: str) -> Booking:
        self._require_capability(BookingCapability.GET_BOOKING)
        resp = await self._http.request(
            "GET",
            f"{CALENDLY_API_BASE}/scheduled_events/{booking_id}",
            headers=await self._auth_headers(),
        )
        event = resp.json().get("resource") or {}
        # Fetch the first invitee for customer info
        inv_resp = await self._http.request(
            "GET",
            f"{CALENDLY_API_BASE}/scheduled_events/{booking_id}/invitees",
            headers=await self._auth_headers(),
            params={"count": 1},
        )
        invitees = inv_resp.json().get("collection") or []
        if invitees:
            return mappers.to_booking_from_invitee(event, invitees[0])
        return mappers.to_booking(event)

    def list_bookings(self, request: ListBookingsRequest) -> AsyncIterator[Booking]:
        return self._iter_bookings(request)

    async def _iter_bookings(self, request: ListBookingsRequest) -> AsyncGenerator[Booking, None]:
        user_uri = await self._get_user_uri()
        params: dict[str, Any] = {"user": user_uri}
        if request.status:
            # Calendly uses 'active' or 'canceled'
            if request.status.value == "cancelled":
                params["status"] = "canceled"
            else:
                params["status"] = "active"
        if request.start:
            params["min_start_time"] = request.start.isoformat()
        if request.end:
            params["max_start_time"] = request.end.isoformat()

        page_size = request.page_size or 100
        params["count"] = page_size
        next_page_token: str | None = None
        headers = await self._auth_headers()
        while True:
            if next_page_token:
                params["page_token"] = next_page_token
            resp = await self._http.request(
                "GET",
                f"{CALENDLY_API_BASE}/scheduled_events",
                headers=headers,
                params=params,
            )
            data = resp.json()
            events = data.get("collection") or []
            for event in events:
                yield mappers.to_booking(event)
            pagination = data.get("pagination") or {}
            next_page_token = pagination.get("next_page_token")
            if not next_page_token or len(events) < page_size:
                break

    async def update_booking(self, request: UpdateBookingRequest) -> Booking:
        self._require_capability(BookingCapability.UPDATE_BOOKING)
        raise Exception("unreachable")  # capability not in set

    async def cancel_booking(self, booking_id: str, reason: str | None = None) -> None:
        body: dict[str, Any] = {}
        if reason:
            body["reason"] = reason
        await self._http.request(
            "POST",
            f"{CALENDLY_API_BASE}/scheduled_events/{booking_id}/cancellation",
            headers=await self._auth_headers(),
            json=body,
        )

    async def reschedule_booking(self, request: RescheduleBookingRequest) -> Booking:
        self._require_capability(BookingCapability.RESCHEDULE_BOOKING)
        raise Exception("unreachable")  # capability not in set

    async def find_customer(self, request: FindCustomerRequest) -> BookingCustomer | None:
        self._require_capability(BookingCapability.CUSTOMER_LOOKUP)
        return None  # unreachable

    async def get_customer(self, customer_id: str) -> BookingCustomer:
        self._require_capability(BookingCapability.CUSTOMER_MANAGEMENT)
        raise Exception("unreachable")  # unreachable

    async def create_customer(self, customer: BookingCustomer) -> BookingCustomer:
        self._require_capability(BookingCapability.CUSTOMER_MANAGEMENT)
        raise Exception("unreachable")
