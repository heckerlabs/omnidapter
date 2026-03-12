"""
Mappers between Zoho Calendar API format and canonical types.

Public API:
  to_calendar_event(raw, calendar_id) -> CalendarEvent
  from_calendar_event(event) -> dict
  to_calendar(raw) -> Calendar
"""

from __future__ import annotations

import contextlib
from datetime import date, datetime, timezone
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
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
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
