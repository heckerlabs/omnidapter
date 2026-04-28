"""Cal.com ↔ Omnidapter model mappers."""

from __future__ import annotations

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
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def _status(raw: str) -> BookingStatus:
    s = raw.lower()
    mapping = {
        "cancelled": BookingStatus.CANCELLED,
        "rejected": BookingStatus.CANCELLED,
        "rescheduled": BookingStatus.CANCELLED,
        "pending": BookingStatus.PENDING,
        "awaiting_host": BookingStatus.PENDING,
    }
    return mapping.get(s, BookingStatus.CONFIRMED)


def to_service_type(data: dict) -> ServiceType:
    return ServiceType(
        id=str(data["id"]),
        name=data["title"],
        description=data.get("description") or None,
        duration_minutes=data.get("length") or data.get("duration"),
        price=str(data["price"]) if data.get("price") else None,
        provider_data=data,
    )


def to_staff_member(data: dict) -> StaffMember:
    profile = data.get("profile") or {}
    return StaffMember(
        id=str(data.get("id", data.get("userId", ""))),
        name=profile.get("name") or data.get("name") or "",
        email=profile.get("email") or data.get("email") or None,
        service_ids=[],
        provider_data=data,
    )


def to_booking(data: dict) -> Booking:
    attendees = data.get("attendees") or []
    primary = attendees[0] if attendees else {}
    customer = BookingCustomer(
        name=primary.get("name") or None,
        email=primary.get("email") or None,
        timezone=primary.get("timeZone") or None,
    )
    start_str = data.get("start") or data.get("startTime", "")
    end_str = data.get("end") or data.get("endTime", "")
    start = parse_dt(start_str) if start_str else datetime.now()
    end = parse_dt(end_str) if end_str else start + timedelta(minutes=30)

    urls: dict[str, str] = {}
    if data.get("cancelUrl") or data.get("cancellationReason"):
        pass
    if data.get("metadata", {}).get("videoCallUrl"):
        urls["manage"] = data["metadata"]["videoCallUrl"]

    return Booking(
        id=str(data.get("uid") or data.get("id", "")),
        service_id=str(data.get("eventTypeId") or data.get("eventType", {}).get("id", "")),
        start=start,
        end=end,
        status=_status(data.get("status", "accepted")),
        customer=customer,
        staff_id=str(data["userId"]) if data.get("userId") else None,
        location_id=None,
        notes=data.get("description") or None,
        management_urls=urls or None,
        provider_data=data,
    )


def to_booking_customer(data: dict) -> BookingCustomer:
    return BookingCustomer(
        email=data.get("email") or None,
        name=data.get("name") or None,
        timezone=data.get("timeZone") or None,
        provider_data=data,
    )


def to_availability_slot(
    time_str: str, service_id: str, duration_minutes: int, staff_id: str | None
) -> AvailabilitySlot:
    start = parse_dt(time_str)
    return AvailabilitySlot(
        start=start,
        end=start + timedelta(minutes=duration_minutes),
        service_id=service_id,
        staff_id=staff_id,
    )
