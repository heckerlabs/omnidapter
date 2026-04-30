"""Calendly ↔ Omnidapter model mappers."""

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
    # Remove microseconds suffix if present: .000000Z → +00:00
    return datetime.fromisoformat(value)


def _event_type_id(uri: str) -> str:
    """Extract UUID from a Calendly URI like https://api.calendly.com/event_types/{uuid}."""
    return uri.rstrip("/").split("/")[-1]


def _status(raw: str) -> BookingStatus:
    s = raw.lower()
    if s in ("canceled", "cancelled"):
        return BookingStatus.CANCELLED
    if s == "no_show":
        return BookingStatus.NO_SHOW
    return BookingStatus.CONFIRMED


def to_service_type(data: dict) -> ServiceType:
    uri = data.get("uri", "")
    return ServiceType(
        id=_event_type_id(uri),
        name=data.get("name", ""),
        description=data.get("description_plain") or None,
        duration_minutes=data.get("duration"),
        price=None,
        provider_data=data,
    )


def to_staff_member(data: dict) -> StaffMember:
    user = data.get("user") or data
    uri = user.get("uri", "")
    return StaffMember(
        id=_event_type_id(uri) if uri else str(user.get("uuid", "")),
        name=user.get("name", ""),
        email=user.get("email") or None,
        service_ids=[],
        provider_data=data,
    )


def to_booking(data: dict) -> Booking:
    uri = data.get("uri", "")
    event_type_uri = data.get("event_type", "")
    service_id = _event_type_id(event_type_uri) if event_type_uri else ""

    start_str = data.get("start_time", "")
    end_str = data.get("end_time", "")
    start = parse_dt(start_str) if start_str else datetime.now()
    end = parse_dt(end_str) if end_str else start + timedelta(minutes=30)

    # Location / organizer info
    organizer = data.get("event_memberships") or [{}]
    organizer_uri = organizer[0].get("user") if organizer else None

    urls: dict[str, str] = {}
    if data.get("calendar_event", {}).get("join_url"):
        urls["manage"] = data["calendar_event"]["join_url"]

    return Booking(
        id=_event_type_id(uri),
        service_id=service_id,
        start=start,
        end=end,
        status=_status(data.get("status", "active")),
        customer=BookingCustomer(),
        staff_id=_event_type_id(organizer_uri) if organizer_uri else None,
        location_id=None,
        notes=data.get("description") or None,
        management_urls=urls or None,
        provider_data=data,
    )


def to_booking_from_invitee(event: dict, invitee: dict) -> Booking:
    """Build a Booking from a scheduled event + invitee."""
    uri = event.get("uri", "")
    event_type_uri = event.get("event_type", "")
    service_id = _event_type_id(event_type_uri) if event_type_uri else ""

    start_str = event.get("start_time", "")
    end_str = event.get("end_time", "")
    start = parse_dt(start_str) if start_str else datetime.now()
    end = parse_dt(end_str) if end_str else start + timedelta(minutes=30)

    cancel_url = invitee.get("cancel_url", "")
    reschedule_url = invitee.get("reschedule_url", "")
    urls: dict[str, str] = {}
    if cancel_url:
        urls["cancel"] = cancel_url
    if reschedule_url:
        urls["reschedule"] = reschedule_url

    return Booking(
        id=_event_type_id(invitee.get("uri", uri)),
        service_id=service_id,
        start=start,
        end=end,
        status=_status(invitee.get("status", "active")),
        customer=BookingCustomer(
            name=invitee.get("name") or None,
            email=invitee.get("email") or None,
            timezone=invitee.get("timezone") or None,
        ),
        staff_id=None,
        location_id=None,
        notes=None,
        management_urls=urls or None,
        provider_data={"event": event, "invitee": invitee},
    )


def to_availability_slot(item: dict, service_id: str, duration_minutes: int) -> AvailabilitySlot:
    start = parse_dt(item["start_time"])
    return AvailabilitySlot(
        start=start,
        end=start + timedelta(minutes=duration_minutes),
        service_id=service_id,
    )
