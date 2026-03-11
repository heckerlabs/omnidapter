"""
Abstract calendar service interface.

All provider calendar implementations must implement this interface.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from omnidapter.services.calendar.capabilities import CalendarCapability
from omnidapter.services.calendar.models import (
    AvailabilityResponse,
    Calendar,
    CalendarEvent,
)
from omnidapter.services.calendar.requests import (
    CreateEventRequest,
    GetAvailabilityRequest,
    UpdateEventRequest,
)


class CalendarService(ABC):
    """Abstract calendar service interface.

    Typed methods, not generic command dispatch.
    """

    @property
    @abstractmethod
    def capabilities(self) -> frozenset[CalendarCapability]:
        """Return the set of capabilities supported by this provider."""
        ...

    def supports(self, capability: CalendarCapability) -> bool:
        """Return True if this provider supports the given capability."""
        return capability in self.capabilities

    def _require_capability(self, capability: CalendarCapability) -> None:
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
    async def list_calendars(self) -> list[Calendar]:
        """List all calendars accessible to this connection."""
        ...

    @abstractmethod
    async def get_availability(
        self, request: GetAvailabilityRequest
    ) -> AvailabilityResponse:
        """Query free/busy availability."""
        ...

    @abstractmethod
    async def create_event(self, request: CreateEventRequest) -> CalendarEvent:
        """Create a new event."""
        ...

    @abstractmethod
    async def update_event(self, request: UpdateEventRequest) -> CalendarEvent:
        """Update an existing event."""
        ...

    @abstractmethod
    async def delete_event(self, calendar_id: str, event_id: str) -> None:
        """Delete an event."""
        ...

    @abstractmethod
    async def get_event(self, calendar_id: str, event_id: str) -> CalendarEvent:
        """Retrieve a single event by ID."""
        ...

    @abstractmethod
    def list_events(
        self,
        calendar_id: str,
        *,
        time_min=None,
        time_max=None,
        page_size: int | None = None,
        extra: dict | None = None,
    ) -> AsyncIterator[CalendarEvent]:
        """Return an async iterator over all events."""
        ...

