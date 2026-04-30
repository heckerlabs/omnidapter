"""Acuity Scheduling ↔ Omnidapter model mappers."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from omnidapter.services.booking.models import (
    AvailabilitySlot,
    Booking,
    BookingCustomer,
    BookingStatus,
    ServiceType,
    StaffMember,
)


def parse_dt(value: str) -> datetime:
    """Parse ISO 8601 datetime, normalizing -HHMM offset to -HH:MM for Python 3.10."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    value = re.sub(r"([+-])(\d{2})(\d{2})$", r"\1\2:\3", value)
    return datetime.fromisoformat(value)


def _status(raw: str) -> BookingStatus:
    s = raw.lower()
    if s in ("cancelled", "canceled"):
        return BookingStatus.CANCELLED
    if s == "pending":
        return BookingStatus.PENDING
    if s in ("no-show", "no_show"):
        return BookingStatus.NO_SHOW
    return BookingStatus.CONFIRMED


def to_service_type(data: dict) -> ServiceType:
    return ServiceType(
        id=str(data["id"]),
        name=data["name"],
        description=data.get("description") or None,
        duration_minutes=data.get("duration"),
        price=str(data["price"]) if data.get("price") is not None else None,
        provider_data=data,
    )


def to_staff_member(data: dict) -> StaffMember:
    return StaffMember(
        id=str(data["id"]),
        name=data["name"],
        email=data.get("email") or None,
        service_ids=[],
        provider_data=data,
    )


def to_booking(data: dict) -> Booking:
    customer = BookingCustomer(
        id=str(data["clientId"]) if data.get("clientId") else None,
        name=f"{data.get('firstName', '')} {data.get('lastName', '')}".strip() or None,
        email=data.get("email") or None,
        phone=data.get("phone") or None,
        timezone=data.get("calendarTimezone") or None,
    )
    start = parse_dt(data["datetime"])
    duration = int(data.get("duration") or 0)
    end = start + timedelta(minutes=duration)

    urls: dict[str, str] = {}
    if data.get("confirmationPage"):
        urls["manage"] = data["confirmationPage"]
    if data.get("cancelUrl"):
        urls["cancel"] = data["cancelUrl"]
    if data.get("rescheduleUrl"):
        urls["reschedule"] = data["rescheduleUrl"]

    return Booking(
        id=str(data["id"]),
        service_id=str(data.get("appointmentTypeID", "")),
        start=start,
        end=end,
        status=_status(data.get("status", "Confirmed")),
        customer=customer,
        staff_id=str(data["calendarID"]) if data.get("calendarID") else None,
        location_id=None,
        notes=data.get("notes") or None,
        management_urls=urls or None,
        provider_data=data,
    )


def to_booking_customer(data: dict) -> BookingCustomer:
    return BookingCustomer(
        id=str(data["id"]),
        name=f"{data.get('firstName', '')} {data.get('lastName', '')}".strip() or None,
        email=data.get("email") or None,
        phone=data.get("phone") or None,
        timezone=data.get("timezone") or None,
        provider_data=data,
    )


def to_availability_slot(
    item: dict, service_id: str, duration_minutes: int, staff_id: str | None
) -> AvailabilitySlot:
    start = parse_dt(item["time"])
    return AvailabilitySlot(
        start=start,
        end=start + timedelta(minutes=duration_minutes),
        service_id=service_id,
        staff_id=staff_id,
    )
