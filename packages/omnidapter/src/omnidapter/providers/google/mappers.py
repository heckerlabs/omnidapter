"""
Mappers between Google Calendar API format and canonical types.

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
    ConferenceData,
    ConferenceEntryPoint,
    EventStatus,
    EventVisibility,
    Organizer,
    Recurrence,
)

# --------------------------------------------------------------------------- #
# Private helpers                                                              #
# --------------------------------------------------------------------------- #


def _parse_event_time(time_obj: dict) -> datetime | date:
    if "dateTime" in time_obj:
        return datetime.fromisoformat(time_obj["dateTime"].replace("Z", "+00:00"))
    if "date" in time_obj:
        return date.fromisoformat(time_obj["date"])
    raise ValueError(f"Unrecognised Google time object: {time_obj}")


def _format_event_time(dt: datetime | date, all_day: bool) -> dict:
    if all_day or (isinstance(dt, date) and not isinstance(dt, datetime)):
        d = dt.date() if isinstance(dt, datetime) else dt
        return {"date": d.isoformat()}
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return {"dateTime": dt.isoformat()}
    return {"date": str(dt)}


def _map_attendee_status(google_status: str) -> AttendeeStatus:
    return {
        "accepted": AttendeeStatus.ACCEPTED,
        "declined": AttendeeStatus.DECLINED,
        "tentative": AttendeeStatus.TENTATIVE,
        "needsAction": AttendeeStatus.NEEDS_ACTION,
    }.get(google_status, AttendeeStatus.UNKNOWN)


_GOOGLE_STATUS = {
    "confirmed": EventStatus.CONFIRMED,
    "tentative": EventStatus.TENTATIVE,
    "cancelled": EventStatus.CANCELLED,
}
_CANONICAL_STATUS_TO_GOOGLE = {v: k for k, v in _GOOGLE_STATUS.items()}

_GOOGLE_VISIBILITY = {
    "public": EventVisibility.PUBLIC,
    "private": EventVisibility.PRIVATE,
    "confidential": EventVisibility.CONFIDENTIAL,
    "default": EventVisibility.DEFAULT,
}
_CANONICAL_VISIBILITY_TO_GOOGLE = {v: k for k, v in _GOOGLE_VISIBILITY.items()}


# --------------------------------------------------------------------------- #
# Public mappers                                                               #
# --------------------------------------------------------------------------- #


def to_calendar_event(raw: dict, calendar_id: str) -> CalendarEvent:
    """Map a raw Google Calendar API event dict to a canonical CalendarEvent."""
    start_obj = raw.get("start", {})
    end_obj = raw.get("end", {})
    start = _parse_event_time(start_obj)
    end = _parse_event_time(end_obj)
    all_day = "date" in start_obj

    organizer_raw = raw.get("organizer")
    organizer = None
    if organizer_raw:
        organizer = Organizer(
            email=organizer_raw.get("email", ""),
            display_name=organizer_raw.get("displayName"),
            is_self=organizer_raw.get("self", False),
        )

    attendees = [
        Attendee(
            email=att.get("email", ""),
            display_name=att.get("displayName"),
            status=_map_attendee_status(att.get("responseStatus", "needsAction")),
            is_organizer=att.get("organizer", False),
            is_self=att.get("self", False),
            is_resource=att.get("resource", False),
            optional=att.get("optional", False),
            comment=att.get("comment"),
        )
        for att in raw.get("attendees", [])
    ]

    recurrence = None
    rules = raw.get("recurrence", [])
    recurring_event_id = raw.get("recurringEventId")
    if rules or recurring_event_id:
        original_start = None
        orig_raw = raw.get("originalStartTime")
        if orig_raw:
            with contextlib.suppress(Exception):
                original_start = _parse_event_time(orig_raw)
        recurrence = Recurrence(
            rules=rules,
            recurring_event_id=recurring_event_id,
            original_start_time=original_start,
        )

    conference_data = None
    conf_raw = raw.get("conferenceData")
    if conf_raw:
        entry_points = [
            ConferenceEntryPoint(
                entry_point_type=ep.get("entryPointType", "video"),
                uri=ep.get("uri", ""),
                label=ep.get("label"),
                pin=ep.get("pin"),
            )
            for ep in conf_raw.get("entryPoints", [])
        ]
        cs = conf_raw.get("conferenceSolution", {})
        conference_data = ConferenceData(
            conference_id=conf_raw.get("conferenceId"),
            conference_solution_name=cs.get("name"),
            entry_points=entry_points,
            join_url=next(
                (ep.uri for ep in entry_points if ep.entry_point_type == "video"),
                None,
            ),
        )

    created_at = None
    if raw.get("created"):
        with contextlib.suppress(Exception):
            created_at = datetime.fromisoformat(raw["created"].replace("Z", "+00:00"))

    updated_at = None
    if raw.get("updated"):
        with contextlib.suppress(Exception):
            updated_at = datetime.fromisoformat(raw["updated"].replace("Z", "+00:00"))

    _MAPPED_KEYS = frozenset(
        {
            "id",
            "summary",
            "description",
            "location",
            "status",
            "visibility",
            "start",
            "end",
            "organizer",
            "attendees",
            "recurrence",
            "recurringEventId",
            "originalStartTime",
            "conferenceData",
            "created",
            "updated",
            "htmlLink",
            "iCalUID",
            "etag",
            "sequence",
        }
    )
    return CalendarEvent(
        event_id=raw["id"],
        calendar_id=calendar_id,
        summary=raw.get("summary"),
        description=raw.get("description"),
        location=raw.get("location"),
        status=_GOOGLE_STATUS.get(raw.get("status", "confirmed"), EventStatus.CONFIRMED),
        visibility=_GOOGLE_VISIBILITY.get(
            raw.get("visibility", "default"), EventVisibility.DEFAULT
        ),
        start=start,
        end=end,
        all_day=all_day,
        timezone=start_obj.get("timeZone"),
        organizer=organizer,
        attendees=attendees,
        recurrence=recurrence,
        conference_data=conference_data,
        created_at=created_at,
        updated_at=updated_at,
        html_link=raw.get("htmlLink"),
        ical_uid=raw.get("iCalUID"),
        etag=raw.get("etag"),
        sequence=raw.get("sequence"),
        provider_data={k: v for k, v in raw.items() if k not in _MAPPED_KEYS},
    )


def from_calendar_event(event: CalendarEvent) -> dict[str, Any]:
    """Map a canonical CalendarEvent to a Google Calendar API event dict."""
    body: dict[str, Any] = {
        "summary": event.summary,
        "start": _format_event_time(event.start, event.all_day),
        "end": _format_event_time(event.end, event.all_day),
    }
    if event.timezone:
        body["start"].setdefault("timeZone", event.timezone)
        body["end"].setdefault("timeZone", event.timezone)
    if event.description is not None:
        body["description"] = event.description
    if event.location is not None:
        body["location"] = event.location
    if event.status and event.status != EventStatus.UNKNOWN:
        body["status"] = _CANONICAL_STATUS_TO_GOOGLE.get(event.status, "confirmed")
    if event.visibility:
        body["visibility"] = _CANONICAL_VISIBILITY_TO_GOOGLE.get(event.visibility, "default")
    if event.attendees:
        body["attendees"] = [
            {"email": a.email, "displayName": a.display_name, "optional": a.optional}
            for a in event.attendees
        ]
    if event.recurrence:
        body["recurrence"] = event.recurrence.rules
    return body


def to_calendar(raw: dict) -> Calendar:
    """Map a raw Google CalendarListEntry to a canonical Calendar."""
    _MAPPED_KEYS = frozenset(
        {
            "id",
            "summary",
            "description",
            "timeZone",
            "primary",
            "accessRole",
            "backgroundColor",
            "foregroundColor",
        }
    )
    return Calendar(
        calendar_id=raw["id"],
        summary=raw.get("summary", ""),
        description=raw.get("description"),
        timezone=raw.get("timeZone"),
        is_primary=raw.get("primary", False),
        is_read_only=raw.get("accessRole", "") in ("reader", "freeBusyReader"),
        background_color=raw.get("backgroundColor"),
        foreground_color=raw.get("foregroundColor"),
        provider_data={k: v for k, v in raw.items() if k not in _MAPPED_KEYS},
    )
