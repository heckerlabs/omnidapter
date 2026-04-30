"""Housecall Pro ↔ Omnidapter model mappers."""

from __future__ import annotations

import contextlib
from datetime import datetime, timedelta

from omnidapter.services.booking.models import (
    AvailabilitySlot,
    Booking,
    BookingCustomer,
    BookingStatus,
    ServiceType,
    StaffMember,
)
from omnidapter.services.crm.models import (
    Activity,
    ActivityKind,
    Contact,
    ContactEmail,
    ContactPhone,
)


def parse_dt(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def _status(raw: str) -> BookingStatus:
    s = raw.lower()
    if s in ("cancelled", "canceled"):
        return BookingStatus.CANCELLED
    if s in ("needs scheduling", "unscheduled"):
        return BookingStatus.PENDING
    return BookingStatus.CONFIRMED


def to_service_type(data: dict) -> ServiceType:
    return ServiceType(
        id=str(data.get("id", "")),
        name=data.get("name", ""),
        description=data.get("description") or None,
        duration_minutes=None,
        price=str(data["price"]) if data.get("price") is not None else None,
        provider_data=data,
    )


def to_staff_member(data: dict) -> StaffMember:
    return StaffMember(
        id=str(data.get("id", "")),
        name=data.get("name")
        or f"{data.get('first_name', '')} {data.get('last_name', '')}".strip(),
        email=data.get("email") or None,
        service_ids=[],
        provider_data=data,
    )


def to_booking(data: dict) -> Booking:
    customer_data = data.get("customer") or {}
    customer = BookingCustomer(
        id=str(customer_data["id"]) if customer_data.get("id") else None,
        name=customer_data.get("name")
        or f"{customer_data.get('first_name', '')} {customer_data.get('last_name', '')}".strip()
        or None,
        email=customer_data.get("email") or None,
        phone=customer_data.get("mobile_number") or customer_data.get("home_number") or None,
    )

    schedule = data.get("schedule") or {}
    start_str = schedule.get("scheduled_start") or ""
    end_str = schedule.get("scheduled_end") or ""
    start = parse_dt(start_str) if start_str else datetime.now()
    end = parse_dt(end_str) if end_str else start + timedelta(hours=1)

    assigned = data.get("assigned_employees") or []
    staff_id = str(assigned[0]["id"]) if assigned else None

    line_items = data.get("line_items") or []
    service_id = str(line_items[0].get("product_id", "")) if line_items else str(data.get("id", ""))

    return Booking(
        id=str(data.get("id", "")),
        service_id=service_id,
        start=start,
        end=end,
        status=_status(data.get("work_status") or data.get("status", "")),
        customer=customer,
        staff_id=staff_id,
        location_id=None,
        notes=data.get("description") or None,
        provider_data=data,
    )


def to_booking_customer(data: dict) -> BookingCustomer:
    return BookingCustomer(
        id=str(data.get("id", "")),
        name=data.get("name")
        or f"{data.get('first_name', '')} {data.get('last_name', '')}".strip()
        or None,
        email=data.get("email") or None,
        phone=data.get("mobile_number") or data.get("home_number") or None,
        provider_data=data,
    )


def to_availability_slot(
    start: datetime, end: datetime, service_id: str, staff_id: str | None
) -> AvailabilitySlot:
    return AvailabilitySlot(
        start=start,
        end=end,
        service_id=service_id,
        staff_id=staff_id,
    )


def to_crm_contact(data: dict) -> Contact:
    emails = []
    if data.get("email"):
        emails = [ContactEmail(address=data["email"])]
    phones = []
    if data.get("mobile_number"):
        phones.append(ContactPhone(number=data["mobile_number"], label="mobile"))
    if data.get("home_number"):
        phones.append(ContactPhone(number=data["home_number"], label="home"))
    return Contact(
        id=str(data.get("id", "")),
        first_name=data.get("first_name") or None,
        last_name=data.get("last_name") or None,
        name=data.get("name")
        or f"{data.get('first_name', '')} {data.get('last_name', '')}".strip()
        or None,
        emails=emails,
        phones=phones,
        tags=data.get("tags") or [],
        notes=data.get("notes") or None,
        provider_data=data,
    )


def to_crm_activity(data: dict, contact_id: str | None = None) -> Activity:
    occurred_at = None
    if created := data.get("created_at"):
        with contextlib.suppress(ValueError, TypeError):
            occurred_at = parse_dt(created)
    return Activity(
        id=str(data.get("id", "")),
        kind=ActivityKind.NOTE,
        body=data.get("content") or data.get("body") or None,
        contact_id=contact_id or str(data.get("customer_id", "")) or None,
        occurred_at=occurred_at,
        provider_data=data,
    )
