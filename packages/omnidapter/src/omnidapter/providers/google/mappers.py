"""
Mappers between Google Calendar API format and canonical types.

Public API:
  to_calendar_event(raw, calendar_id) -> CalendarEvent
  from_calendar_event(event) -> dict
  to_calendar(raw) -> Calendar
  from_create_calendar_request(request) -> dict
  from_update_calendar_request(request) -> dict
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import date, datetime, timedelta, timezone
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
    Reminder,
    ReminderOverride,
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


def _infer_google_timezone(dt: datetime | date) -> str | None:
    if not isinstance(dt, datetime):
        return None
    tzinfo = dt.tzinfo
    if tzinfo is None:
        return "UTC"

    zone_key = getattr(tzinfo, "key", None)
    if isinstance(zone_key, str) and zone_key:
        return zone_key

    zone_name = getattr(tzinfo, "zone", None)
    if isinstance(zone_name, str) and zone_name:
        return zone_name

    offset = dt.utcoffset()
    if offset == timedelta(0):
        return "UTC"
    return "UTC"


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

    reminders = None
    reminders_raw = raw.get("reminders")
    if reminders_raw:
        reminders = Reminder(
            use_default=bool(reminders_raw.get("useDefault", False)),
            overrides=[
                ReminderOverride(
                    method=override.get("method", "popup"),
                    minutes_before=int(override.get("minutes", 0)),
                )
                for override in reminders_raw.get("overrides", [])
            ],
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
            "reminders",
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
        reminders=reminders,
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
    elif event.recurrence:
        inferred_tz = _infer_google_timezone(event.start)
        if inferred_tz:
            body["start"].setdefault("timeZone", inferred_tz)
            body["end"].setdefault("timeZone", inferred_tz)
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
    if event.conference_data:
        conference_data = dict(event.conference_data.provider_data or {})
        if "createRequest" not in conference_data:
            conference_data["createRequest"] = {
                "requestId": uuid.uuid4().hex,
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        body["conferenceData"] = conference_data
    if event.reminders:
        reminders: dict[str, Any] = {"useDefault": event.reminders.use_default}
        if event.reminders.overrides:
            reminders["overrides"] = [
                {"method": override.method, "minutes": override.minutes_before}
                for override in event.reminders.overrides
            ]
        body["reminders"] = reminders
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


def from_create_calendar_request(request) -> dict[str, Any]:
    """Map a create-calendar request to Google Calendar API payload."""
    body: dict[str, Any] = {"summary": request.summary}
    if request.description is not None:
        body["description"] = request.description
    if request.timezone is not None:
        body["timeZone"] = request.timezone
    if request.background_color is not None:
        body["backgroundColor"] = request.background_color
    if request.foreground_color is not None:
        body["foregroundColor"] = request.foreground_color
    body.update(request.extra)
    return body


def from_update_calendar_request(request) -> dict[str, Any]:
    """Map an update-calendar request to Google Calendar API payload."""
    body: dict[str, Any] = {}
    if request.summary is not None:
        body["summary"] = request.summary
    if request.description is not None:
        body["description"] = request.description
    if request.timezone is not None:
        body["timeZone"] = request.timezone
    if request.background_color is not None:
        body["backgroundColor"] = request.background_color
    if request.foreground_color is not None:
        body["foregroundColor"] = request.foreground_color
    body.update(request.extra)
    return body
