"""
Booking service request models.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from omnidapter.services.booking.models import BookingCustomer, BookingStatus


class CreateBookingRequest(BaseModel):
    """Request to create a new booking.

    Set ``customer.id`` to bypass find-or-create when the caller already holds
    a customer ID from a previous lookup.
    """

    service_id: str
    start: datetime
    customer: BookingCustomer
    staff_id: str | None = None
    location_id: str | None = None
    notes: str | None = None
    service_ids: list[str] | None = None  # additional service IDs for multi-service bookings
    provider_data: dict[str, Any] | None = None


class UpdateBookingRequest(BaseModel):
    """Request to update an existing booking (partial update — None fields are unchanged)."""

    booking_id: str
    start: datetime | None = None
    staff_id: str | None = None
    location_id: str | None = None
    notes: str | None = None
    status: BookingStatus | None = None
    provider_data: dict[str, Any] | None = None


class RescheduleBookingRequest(BaseModel):
    """Request to reschedule a booking to a new start time."""

    booking_id: str
    new_start: datetime
    new_staff_id: str | None = None


class ListBookingsRequest(BaseModel):
    """Filter criteria for listing bookings."""

    start: datetime | None = None
    end: datetime | None = None
    status: BookingStatus | None = None
    customer_email: str | None = None
    staff_id: str | None = None
    service_id: str | None = None
    location_id: str | None = None
    page_size: int | None = None


class FindCustomerRequest(BaseModel):
    """Criteria for finding an existing customer."""

    email: str | None = None
    phone: str | None = None
    name: str | None = None
