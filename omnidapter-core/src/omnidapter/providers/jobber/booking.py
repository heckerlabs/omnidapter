"""Jobber booking service implementation (GraphQL)."""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from datetime import datetime, timedelta
from typing import Any

from omnidapter.auth.models import OAuth2Credentials
from omnidapter.core.errors import ProviderAPIError
from omnidapter.providers.jobber import mappers
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
from omnidapter.transport.correlation import new_correlation_id
from omnidapter.transport.retry import RetryPolicy

JOBBER_GRAPHQL_URL = "https://api.getjobber.com/api/graphql"
_JOBBER_VERSION = "2024-01-01"

_JOBBER_CAPABILITIES = frozenset(
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


class JobberBookingService(BookingService):
    """Jobber GraphQL API booking service."""

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
            provider_key="jobber",
            retry_policy=retry_policy,
            hooks=hooks,
            default_headers={"X-JOBBER-GRAPHQL-VERSION": _JOBBER_VERSION},
        )

    @property
    def capabilities(self) -> frozenset[BookingCapability]:
        return _JOBBER_CAPABILITIES

    @property
    def _provider_key(self) -> str:
        return "jobber"

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

    async def _graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"query": query}
        if variables:
            body["variables"] = variables
        resp = await self._http.request(
            "POST",
            JOBBER_GRAPHQL_URL,
            headers=await self._auth_headers(),
            json=body,
        )
        result = resp.json()
        if errors := result.get("errors"):
            raise ProviderAPIError(
                f"Jobber GraphQL error: {errors[0].get('message', 'Unknown error')}",
                provider_key="jobber",
                response_body=str(errors),
                correlation_id=new_correlation_id(),
            )
        return result.get("data") or {}

    async def list_services(self, location_id: str | None = None) -> list[ServiceType]:
        query = """
        query ListServices($first: Int) {
          products(first: $first) {
            nodes {
              id
              name
              description
              defaultUnitCost
            }
          }
        }
        """
        data = await self._graphql(query, {"first": 100})
        nodes = (data.get("products") or {}).get("nodes") or []
        return [mappers.to_service_type(n) for n in nodes]

    async def get_service_type(self, service_id: str) -> ServiceType:
        query = """
        query GetService($id: ID!) {
          product(id: $id) {
            id
            name
            description
            defaultUnitCost
          }
        }
        """
        data = await self._graphql(query, {"id": service_id})
        return mappers.to_service_type(data.get("product") or {})

    async def list_staff(
        self,
        service_id: str | None = None,
        location_id: str | None = None,
    ) -> list[StaffMember]:
        query = """
        query ListUsers($first: Int) {
          users(first: $first) {
            nodes {
              id
              name
              email
            }
          }
        }
        """
        data = await self._graphql(query, {"first": 100})
        nodes = (data.get("users") or {}).get("nodes") or []
        return [mappers.to_staff_member(n) for n in nodes]

    async def get_staff(self, staff_id: str) -> StaffMember:
        query = """
        query GetUser($id: ID!) {
          user(id: $id) {
            id
            name
            email
          }
        }
        """
        data = await self._graphql(query, {"id": staff_id})
        return mappers.to_staff_member(data.get("user") or {})

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
        # Compute availability by fetching existing visits in range and finding free time
        query = """
        query ListVisits($filter: VisitFilterAttributes) {
          visits(filter: $filter, first: 200) {
            nodes {
              id
              startAt
              endAt
              isComplete
            }
          }
        }
        """
        variables: dict[str, Any] = {
            "filter": {
                "startAt": {"gte": start.isoformat()},
                "endAt": {"lte": end.isoformat()},
            }
        }
        if staff_id:
            variables["filter"]["assignedUsers"] = [staff_id]

        data = await self._graphql(query, variables)
        booked_visits = (data.get("visits") or {}).get("nodes") or []

        # Build free slots: 9 AM to 5 PM per day, 1-hour slots by default
        slot_duration = timedelta(hours=1)
        booked_ranges = [
            (mappers.parse_dt(v["startAt"]), mappers.parse_dt(v["endAt"]))
            for v in booked_visits
            if v.get("startAt") and v.get("endAt")
        ]

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
            slot_start = max(day_start, start)
            while slot_start + slot_duration <= min(day_end, end):
                slot_end = slot_start + slot_duration
                # Check for overlap with booked visits
                overlaps = any(
                    not (slot_end <= b_start or slot_start >= b_end)
                    for b_start, b_end in booked_ranges
                )
                if not overlaps:
                    slots.append(mappers.to_availability_slot(slot_start, slot_end, service_id))
                slot_start += slot_duration
            if current_day.month == 12 and current_day.day == 31:
                current_day = current_day.replace(year=current_day.year + 1, month=1, day=1)
            else:
                from datetime import date

                current_day = date(
                    current_day.year, current_day.month, current_day.day
                ) + timedelta(days=1)
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
        mutation = """
        mutation CreateJob($input: JobCreateInput!) {
          jobCreate(input: $input) {
            job {
              id
              title
              jobStatus
              client {
                id
                name
              }
              visits {
                nodes {
                  id
                  startAt
                  endAt
                }
              }
            }
            userErrors {
              message
              path
            }
          }
        }
        """
        visit_input: dict[str, Any] = {
            "startAt": request.start.isoformat(),
        }
        job_input: dict[str, Any] = {
            "clientId": customer.id,
            "visits": [visit_input],
        }
        if request.notes:
            job_input["instructions"] = request.notes
        if request.service_id:
            job_input["lineItems"] = [{"productOrServiceId": request.service_id, "quantity": 1}]

        data = await self._graphql(mutation, {"input": job_input})
        result = data.get("jobCreate") or {}
        if errors := result.get("userErrors"):
            raise ProviderAPIError(
                f"Jobber job creation failed: {errors[0].get('message', '')}",
                provider_key="jobber",
                correlation_id=new_correlation_id(),
            )
        return mappers.to_booking(result.get("job") or {})

    async def get_booking(self, booking_id: str) -> Booking:
        query = """
        query GetJob($id: ID!) {
          job(id: $id) {
            id
            title
            jobStatus
            instructions
            client {
              id
              name
              emails { address }
              phones { number }
            }
            visits(first: 1) {
              nodes {
                id
                startAt
                endAt
              }
            }
            lineItems {
              nodes {
                linkedProductOrService { id }
              }
            }
            assignedTo {
              nodes { id name email }
            }
          }
        }
        """
        data = await self._graphql(query, {"id": booking_id})
        return mappers.to_booking(data.get("job") or {})

    def list_bookings(self, request: ListBookingsRequest) -> AsyncIterator[Booking]:
        return self._iter_bookings(request)

    async def _iter_bookings(self, request: ListBookingsRequest) -> AsyncGenerator[Booking, None]:
        query = """
        query ListJobs($first: Int, $after: String, $filter: JobFilterAttributes) {
          jobs(first: $first, after: $after, filter: $filter) {
            nodes {
              id
              title
              jobStatus
              instructions
              client {
                id
                name
                emails { address }
                phones { number }
              }
              visits(first: 1) {
                nodes { id startAt endAt }
              }
              lineItems {
                nodes {
                  linkedProductOrService { id }
                }
              }
              assignedTo {
                nodes { id name email }
              }
            }
            pageInfo {
              hasNextPage
              endCursor
            }
          }
        }
        """
        page_size = request.page_size or 50
        variables: dict[str, Any] = {"first": page_size, "filter": {}}
        if request.status:
            variables["filter"]["jobStatus"] = request.status.value.upper()

        cursor: str | None = None
        while True:
            if cursor:
                variables["after"] = cursor
            data = await self._graphql(query, variables)
            jobs_data = data.get("jobs") or {}
            nodes = jobs_data.get("nodes") or []
            for node in nodes:
                yield mappers.to_booking(node)
            page_info = jobs_data.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")

    async def update_booking(self, request: UpdateBookingRequest) -> Booking:
        mutation = """
        mutation UpdateJob($input: JobEditInput!) {
          jobEdit(input: $input) {
            job {
              id
              title
              jobStatus
              visits(first: 1) {
                nodes { id startAt endAt }
              }
              client { id name }
            }
            userErrors { message }
          }
        }
        """
        job_input: dict[str, Any] = {"id": request.booking_id}
        if request.notes is not None:
            job_input["instructions"] = request.notes

        data = await self._graphql(mutation, {"input": job_input})
        result = data.get("jobEdit") or {}
        return mappers.to_booking(result.get("job") or {})

    async def cancel_booking(self, booking_id: str, reason: str | None = None) -> None:
        mutation = """
        mutation CancelJob($input: JobArchiveInput!) {
          jobArchive(input: $input) {
            job { id jobStatus }
            userErrors { message }
          }
        }
        """
        await self._graphql(mutation, {"input": {"id": booking_id}})

    async def reschedule_booking(self, request: RescheduleBookingRequest) -> Booking:
        # Update the first visit's start time
        # First get the visit ID
        current = await self.get_booking(request.booking_id)
        visit_id = (current.provider_data or {}).get("visits", {}).get("nodes", [{}])[0].get("id")
        if visit_id:
            mutation = """
            mutation UpdateVisit($input: VisitEditInput!) {
              visitEdit(input: $input) {
                visit { id startAt endAt }
                userErrors { message }
              }
            }
            """
            await self._graphql(
                mutation,
                {
                    "input": {
                        "id": visit_id,
                        "startAt": request.new_start.isoformat(),
                    }
                },
            )
        return await self.get_booking(request.booking_id)

    async def find_customer(self, request: FindCustomerRequest) -> BookingCustomer | None:
        query = """
        query FindClient($searchTerm: String) {
          clients(searchTerm: $searchTerm, first: 1) {
            nodes {
              id
              name
              emails { address }
              phones { number }
            }
          }
        }
        """
        search = request.email or request.phone or request.name or ""
        if not search:
            return None
        data = await self._graphql(query, {"searchTerm": search})
        nodes = (data.get("clients") or {}).get("nodes") or []
        if nodes:
            return mappers.to_booking_customer(nodes[0])
        return None

    async def get_customer(self, customer_id: str) -> BookingCustomer:
        query = """
        query GetClient($id: ID!) {
          client(id: $id) {
            id
            name
            emails { address }
            phones { number }
          }
        }
        """
        data = await self._graphql(query, {"id": customer_id})
        return mappers.to_booking_customer(data.get("client") or {})

    async def create_customer(self, customer: BookingCustomer) -> BookingCustomer:
        mutation = """
        mutation CreateClient($input: ClientCreateInput!) {
          clientCreate(input: $input) {
            client {
              id
              name
              emails { address }
              phones { number }
            }
            userErrors { message }
          }
        }
        """
        name_parts = (customer.name or "").split(" ", 1)
        client_input: dict[str, Any] = {
            "firstName": name_parts[0],
            "lastName": name_parts[1] if len(name_parts) > 1 else "",
        }
        if customer.email:
            client_input["emails"] = [{"address": customer.email, "primary": True}]
        if customer.phone:
            client_input["phones"] = [{"number": customer.phone, "primary": True}]

        data = await self._graphql(mutation, {"input": client_input})
        result = data.get("clientCreate") or {}
        if errors := result.get("userErrors"):
            raise ProviderAPIError(
                f"Jobber client creation failed: {errors[0].get('message', '')}",
                provider_key="jobber",
                correlation_id=new_correlation_id(),
            )
        return mappers.to_booking_customer(result.get("client") or {})
