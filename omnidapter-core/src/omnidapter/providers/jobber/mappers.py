"""Jobber ↔ Omnidapter model mappers."""

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
    s = raw.upper()
    if s in ("CANCELLED", "ARCHIVED"):
        return BookingStatus.CANCELLED
    if s in ("REQUIRES_INVOICING", "LATE", "OVERDUE"):
        return BookingStatus.CONFIRMED
    return BookingStatus.CONFIRMED


def to_service_type(data: dict) -> ServiceType:
    return ServiceType(
        id=str(data.get("id", "")),
        name=data.get("name") or data.get("title", ""),
        description=data.get("description") or None,
        duration_minutes=None,
        price=str(data["defaultUnitCost"]) if data.get("defaultUnitCost") else None,
        provider_data=data,
    )


def to_staff_member(data: dict) -> StaffMember:
    return StaffMember(
        id=str(data.get("id", "")),
        name=data.get("name") or f"{data.get('firstName', '')} {data.get('lastName', '')}".strip(),
        email=data.get("email") or None,
        service_ids=[],
        provider_data=data,
    )


def to_booking(data: dict) -> Booking:
    client = data.get("client") or {}
    customer = BookingCustomer(
        id=str(client["id"]) if client.get("id") else None,
        name=client.get("name") or None,
        email=(client.get("emails") or [{}])[0].get("address") if client.get("emails") else None,
        phone=(client.get("phones") or [{}])[0].get("number") if client.get("phones") else None,
    )

    visits = (data.get("visits") or {}).get("nodes") or []
    visit = visits[0] if visits else {}
    start_str = visit.get("startAt") or data.get("startAt", "")
    end_str = visit.get("endAt") or data.get("endAt", "")
    start = parse_dt(start_str) if start_str else datetime.now()
    end = parse_dt(end_str) if end_str else start + timedelta(hours=1)

    assigned = (data.get("assignedTo") or {}).get("nodes") or []
    staff_id = str(assigned[0]["id"]) if assigned else None

    line_items = (data.get("lineItems") or {}).get("nodes") or []
    service_id = (
        str(line_items[0].get("linkedProductOrService", {}).get("id", "")) if line_items else ""
    )

    return Booking(
        id=str(data.get("id", "")),
        service_id=service_id,
        start=start,
        end=end,
        status=_status(data.get("jobStatus") or data.get("status", "")),
        customer=customer,
        staff_id=staff_id,
        location_id=None,
        notes=data.get("instructions") or data.get("description") or None,
        provider_data=data,
    )


def to_booking_customer(data: dict) -> BookingCustomer:
    emails = data.get("emails") or []
    phones = data.get("phones") or []
    return BookingCustomer(
        id=str(data.get("id", "")),
        name=data.get("name") or None,
        email=emails[0].get("address") if emails else None,
        phone=phones[0].get("number") if phones else None,
        provider_data=data,
    )


def to_availability_slot(start: datetime, end: datetime, service_id: str) -> AvailabilitySlot:
    return AvailabilitySlot(
        start=start,
        end=end,
        service_id=service_id,
    )
