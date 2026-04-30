"""
Mappers between Zoho API formats and canonical types.

Calendar public API:
  to_calendar_event(raw, calendar_id) -> CalendarEvent
  from_calendar_event(event) -> dict
  to_calendar(raw) -> Calendar
  from_create_calendar_request(request) -> dict
  from_update_calendar_request(request) -> dict

Bookings public API:
  parse_booking_dt(value) -> datetime | None
  fmt_booking_dt(dt) -> str
  fmt_booking_date(dt) -> str
  to_booking_status(raw) -> BookingStatus
  to_service_type(data) -> ServiceType
  to_staff_member(data) -> StaffMember
  to_booking_customer(data) -> BookingCustomer
  to_booking(data) -> Booking
"""

from __future__ import annotations

import contextlib
from datetime import date, datetime, timedelta, timezone
from typing import Any

from omnidapter.services.calendar.models import (
    Attendee,
    AttendeeStatus,
    Calendar,
    CalendarEvent,
    EventStatus,
)

# --------------------------------------------------------------------------- #
# Private helpers                                                              #
# --------------------------------------------------------------------------- #


def _parse_zoho_datetime(dt_str: str | None) -> datetime | None:
    if not dt_str:
        return None
    try:
        return datetime.strptime(dt_str, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    with_timezone = None
    with contextlib.suppress(ValueError):
        with_timezone = datetime.strptime(dt_str, "%Y%m%dT%H%M%S%z")
    if with_timezone is not None:
        return with_timezone
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        return None


def _format_zoho_datetime(dt: datetime | date) -> str:
    if isinstance(dt, datetime):
        dt = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
        return dt.strftime("%Y%m%dT%H%M%SZ")
    return dt.strftime("%Y%m%d")


# --------------------------------------------------------------------------- #
# Public mappers                                                               #
# --------------------------------------------------------------------------- #


def to_calendar_event(raw: dict, calendar_id: str) -> CalendarEvent:
    """Map a raw Zoho Calendar event dict to a canonical CalendarEvent."""
    date_and_time = raw.get("dateandtime", {})
    start = _parse_zoho_datetime(date_and_time.get("start")) or datetime.now(tz=timezone.utc)
    end = _parse_zoho_datetime(date_and_time.get("end")) or datetime.now(tz=timezone.utc)

    attendees = [
        Attendee(
            email=email,
            display_name=att.get("name"),
            status=AttendeeStatus.NEEDS_ACTION,
        )
        for att in raw.get("attendees", [])
        if (email := str(att.get("email", "")).strip())
    ]

    _MAPPED_KEYS = frozenset(
        {
            "uid",
            "id",
            "title",
            "description",
            "location",
            "dateandtime",
            "attendees",
            "isallday",
        }
    )
    return CalendarEvent(
        event_id=raw.get("uid", raw.get("id", "")),
        calendar_id=calendar_id,
        summary=raw.get("title"),
        description=raw.get("description"),
        location=raw.get("location"),
        status=EventStatus.CONFIRMED,
        start=start,
        end=end,
        all_day=raw.get("isallday", False),
        attendees=attendees,
        provider_data={k: v for k, v in raw.items() if k not in _MAPPED_KEYS},
    )


def from_calendar_event(event: CalendarEvent) -> dict[str, Any]:
    """Map a canonical CalendarEvent to a Zoho Calendar API event dict."""
    body: dict[str, Any] = {
        "title": event.summary,
        "dateandtime": {
            "start": _format_zoho_datetime(event.start),
            "end": _format_zoho_datetime(event.end),
        },
        "isallday": event.all_day,
    }
    if event.description is not None:
        body["description"] = event.description
    if event.location is not None:
        body["location"] = event.location
    if event.attendees:
        body["attendees"] = [{"email": a.email} for a in event.attendees]
    return body


def to_calendar(raw: dict) -> Calendar:
    """Map a raw Zoho calendar dict to a canonical Calendar."""
    _MAPPED_KEYS = frozenset({"uid", "id", "name", "description", "timezone", "isprimary"})
    return Calendar(
        calendar_id=raw.get("uid", raw.get("id", "")),
        summary=raw.get("name", ""),
        description=raw.get("description"),
        timezone=raw.get("timezone"),
        is_primary=raw.get("isprimary", False),
        provider_data={k: v for k, v in raw.items() if k not in _MAPPED_KEYS},
    )


def from_create_calendar_request(request) -> dict[str, Any]:
    """Map a create-calendar request to Zoho Calendar payload."""
    body: dict[str, Any] = {
        "name": request.summary,
        # Zoho's create API requires a color field.
        "color": request.background_color or "#8CBF40",
    }
    if request.description is not None:
        body["description"] = request.description
    if request.timezone is not None:
        body["timezone"] = request.timezone
    if request.background_color is not None:
        body["color"] = request.background_color
    body.update(request.extra)
    return body


def from_update_calendar_request(request) -> dict[str, Any]:
    """Map an update-calendar request to Zoho Calendar payload."""
    body: dict[str, Any] = {}
    if request.summary is not None:
        body["name"] = request.summary
    if request.description is not None:
        body["description"] = request.description
    if request.timezone is not None:
        body["timezone"] = request.timezone
    if request.background_color is not None:
        body["color"] = request.background_color
    body.update(request.extra)
    return body


# --------------------------------------------------------------------------- #
# Bookings helpers and mappers                                                 #
# --------------------------------------------------------------------------- #

from omnidapter.services.booking.models import (  # noqa: E402
    Booking,
    BookingCustomer,
    BookingStatus,
    ServiceType,
    StaffMember,
)

# Zoho Bookings uses "30-Apr-2026 14:30:00" / "30-Apr-2026" formats.
_BOOKING_DT_FMT = "%d-%b-%Y %H:%M:%S"
_BOOKING_DATE_FMT = "%d-%b-%Y"


def parse_booking_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in (_BOOKING_DT_FMT, _BOOKING_DATE_FMT, "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
        with contextlib.suppress(ValueError, TypeError):
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
    return None


def fmt_booking_dt(dt: datetime) -> str:
    return dt.strftime(_BOOKING_DT_FMT)


def fmt_booking_date(dt: datetime) -> str:
    return dt.strftime(_BOOKING_DATE_FMT)


def to_booking_status(raw: str | None) -> BookingStatus:
    mapping = {
        "scheduled": BookingStatus.CONFIRMED,
        "cancelled": BookingStatus.CANCELLED,
        "noshow": BookingStatus.NO_SHOW,
    }
    return mapping.get((raw or "").lower(), BookingStatus.CONFIRMED)


def to_service_type(data: dict) -> ServiceType:
    return ServiceType(
        id=str(data.get("id", "")),
        name=data.get("name") or "",
        description=data.get("description") or None,
        duration_minutes=data.get("duration") or None,
        price=str(data["cost"]) if data.get("cost") is not None else None,
        provider_data=data,
    )


def to_staff_member(data: dict) -> StaffMember:
    return StaffMember(
        id=str(data.get("id", "")),
        name=data.get("name") or "",
        email=data.get("email") or None,
        service_ids=[str(s) for s in (data.get("assigned_services") or [])],
        provider_data=data,
    )


def to_booking_customer(data: dict) -> BookingCustomer:
    return BookingCustomer(
        id=data.get("customer_id") or data.get("customer_email") or None,
        name=data.get("customer_name") or (data.get("customer_details") or {}).get("name"),
        email=data.get("customer_email") or (data.get("customer_details") or {}).get("email"),
        phone=data.get("customer_contact_no")
        or (data.get("customer_details") or {}).get("phone_number"),
        provider_data=data,
    )


def to_booking(data: dict) -> Booking:
    start = parse_booking_dt(data.get("appointment_start_time")) or datetime.now(tz=timezone.utc)
    duration = data.get("duration") or 60
    end = parse_booking_dt(data.get("appointment_end_time")) or (
        start + timedelta(minutes=duration)
    )
    customer_data = dict(data)
    if "customer_details" in data and isinstance(data["customer_details"], dict):
        customer_data.update(data["customer_details"])
    return Booking(
        id=str(data.get("booking_id", "")),
        service_id=str(data.get("service_id") or data.get("service_name") or ""),
        start=start,
        end=end,
        status=to_booking_status(data.get("status")),
        customer=to_booking_customer(customer_data),
        staff_id=str(data.get("staff_id") or data.get("staff_name") or "") or None,
        notes=data.get("notes") or None,
        management_urls={"manage": data["summary_url"]} if data.get("summary_url") else None,
        provider_data=data,
    )
