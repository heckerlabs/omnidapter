"""
Booking service domain models.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


class BookingStatus(str, Enum):
    """Status of a booking."""

    CONFIRMED = "confirmed"
    PENDING = "pending"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class BookingCustomer(BaseModel):
    """A customer associated with a booking.

    ``id`` is None when creating a booking without a pre-existing customer record.
    Set ``id`` on ``CreateBookingRequest.customer`` to bypass find-or-create.
    """

    id: str | None = None
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    timezone: str | None = None
    provider_data: dict[str, Any] | None = None


class BookingCustomerCreate(BaseModel):
    """Input for creating a new customer record."""

    name: str | None = None
    email: str | None = None
    phone: str | None = None
    timezone: str | None = None
    provider_data: dict[str, Any] | None = None


class StaffMember(BaseModel):
    """A bookable staff member."""

    id: str
    name: str
    email: str | None = None
    service_ids: list[str] = []
    provider_data: dict[str, Any] | None = None


class ServiceType(BaseModel):
    """A bookable service offered by the provider."""

    id: str
    name: str
    description: str | None = None
    duration_minutes: int | None = None
    price: str | None = None
    provider_data: dict[str, Any] | None = None


class BookingLocation(BaseModel):
    """A physical or virtual location where bookings can occur."""

    id: str
    name: str
    address: str | None = None
    provider_data: dict[str, Any] | None = None


class AvailabilitySlot(BaseModel):
    """A single bookable time slot."""

    start: datetime
    end: datetime
    service_id: str
    staff_id: str | None = None
    location_id: str | None = None


class Booking(BaseModel):
    """A confirmed or pending booking appointment.

    ``management_urls`` carries provider-specific action URLs.
    Well-known keys: ``"cancel"``, ``"reschedule"``, ``"manage"``, ``"confirm"``.
    """

    id: str
    service_id: str
    start: datetime
    end: datetime
    status: BookingStatus
    customer: BookingCustomer
    staff_id: str | None = None
    location_id: str | None = None
    notes: str | None = None
    management_urls: dict[str, str] | None = None
    provider_data: dict[str, Any] | None = None
