"""
Abstract booking service interface.

All provider booking implementations must implement this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import datetime

from omnidapter.services.booking.capabilities import BookingCapability
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


class BookingService(ABC):
    """Abstract booking service interface."""

    @property
    @abstractmethod
    def capabilities(self) -> frozenset[BookingCapability]:
        """Return the set of capabilities supported by this provider."""
        ...

    def supports(self, capability: BookingCapability) -> bool:
        """Return True if this provider supports the given capability."""
        return capability in self.capabilities

    def _require_capability(self, capability: BookingCapability) -> None:
        """Raise UnsupportedCapabilityError if capability is not supported."""
        if not self.supports(capability):
            from omnidapter.core.errors import UnsupportedCapabilityError

            raise UnsupportedCapabilityError(
                f"Capability {capability.value!r} is not supported by this provider",
                provider_key=self._provider_key,
                capability=capability,
            )

    @property
    @abstractmethod
    def _provider_key(self) -> str:
        """Return the provider key for error context."""
        ...

    @abstractmethod
    async def list_services(self, location_id: str | None = None) -> list[ServiceType]:
        """List bookable service types offered by this provider."""
        ...

    @abstractmethod
    async def get_service_type(self, service_id: str) -> ServiceType:
        """Retrieve a single service type by ID."""
        ...

    @abstractmethod
    async def list_staff(
        self,
        service_id: str | None = None,
        location_id: str | None = None,
    ) -> list[StaffMember]:
        """List bookable staff members, optionally filtered by service or location."""
        ...

    @abstractmethod
    async def get_staff(self, staff_id: str) -> StaffMember:
        """Retrieve a single staff member by ID."""
        ...

    @abstractmethod
    async def list_locations(self) -> list[BookingLocation]:
        """List all locations where bookings can be made."""
        ...

    @abstractmethod
    async def get_availability(
        self,
        service_id: str,
        start: datetime,
        end: datetime,
        staff_id: str | None = None,
        location_id: str | None = None,
        timezone: str | None = None,
    ) -> list[AvailabilitySlot]:
        """Return available booking slots for the given criteria."""
        ...

    @abstractmethod
    async def create_booking(self, request: CreateBookingRequest) -> Booking:
        """Create a new booking.

        Implementations call ``_resolve_customer()`` internally to handle
        find-or-create for providers that require a customer record.
        """
        ...

    @abstractmethod
    async def get_booking(self, booking_id: str) -> Booking:
        """Retrieve a booking by ID."""
        ...

    @abstractmethod
    def list_bookings(self, request: ListBookingsRequest) -> AsyncIterator[Booking]:
        """Return an async iterator over bookings matching the given criteria."""
        ...

    @abstractmethod
    async def update_booking(self, request: UpdateBookingRequest) -> Booking:
        """Update an existing booking (partial update)."""
        ...

    @abstractmethod
    async def cancel_booking(self, booking_id: str, reason: str | None = None) -> None:
        """Cancel a booking."""
        ...

    @abstractmethod
    async def reschedule_booking(self, request: RescheduleBookingRequest) -> Booking:
        """Reschedule a booking to a new time."""
        ...

    @abstractmethod
    async def find_customer(self, request: FindCustomerRequest) -> BookingCustomer | None:
        """Look up an existing customer by email, phone, or name. Returns None if not found."""
        ...

    @abstractmethod
    async def get_customer(self, customer_id: str) -> BookingCustomer:
        """Retrieve a customer record by ID."""
        ...

    @abstractmethod
    async def create_customer(self, customer: BookingCustomer) -> BookingCustomer:
        """Create a new customer record and return it with a populated ``id``."""
        ...
