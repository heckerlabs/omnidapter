"""
Mappers between Microsoft Graph Calendar API format and canonical types.

Public API:
  to_calendar_event(raw, calendar_id) -> CalendarEvent
  from_calendar_event(event) -> dict
  to_calendar(raw) -> Calendar
"""

from __future__ import annotations

import contextlib
import html
import re
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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


def _parse_ms_datetime(obj: dict | None) -> datetime | None:
    if not obj:
        return None
    dt_str = obj.get("dateTime")
    if not dt_str:
        return None
    dt_str = dt_str.split(".")[0]  # strip fractional seconds
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            tz_str = obj.get("timeZone")
            if tz_str:
                try:
                    dt = dt.replace(tzinfo=ZoneInfo(tz_str))
                except ZoneInfoNotFoundError:
                    # Windows timezone names (e.g. "Eastern Standard Time") are not
                    # recognised by zoneinfo; fall back to UTC.
                    dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _format_ms_datetime(dt: datetime | date, tz: str | None) -> dict:
    if isinstance(dt, datetime):
        return {"dateTime": dt.isoformat(), "timeZone": tz or "UTC"}
    return {"dateTime": f"{dt}T00:00:00", "timeZone": tz or "UTC"}


def _extract_body_content(body: dict[str, Any] | None) -> str | None:
    if not body:
        return None
    content = body.get("content")
    if not isinstance(content, str):
        return None
    content_type = str(body.get("contentType") or "").lower()
    if content_type != "html":
        return content

    text = re.sub(r"<br\s*/?>", "\n", content, flags=re.IGNORECASE)
    text = re.sub(r"</(p|div|li|tr|h[1-6])>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


_MS_STATUS = {
    "normal": EventStatus.CONFIRMED,
    "busy": EventStatus.CONFIRMED,
    "free": EventStatus.CONFIRMED,
    "oof": EventStatus.CONFIRMED,
    "workingElsewhere": EventStatus.CONFIRMED,
    "unknown": EventStatus.CONFIRMED,
    "tentative": EventStatus.TENTATIVE,
}
_CANONICAL_STATUS_TO_MS = {
    EventStatus.CONFIRMED: "busy",
    EventStatus.TENTATIVE: "tentative",
    # Graph does not accept "cancelled" in showAs. Cancellation is represented
    # by event lifecycle/endpoints, not free/busy status.
    EventStatus.CANCELLED: "busy",
}

_MS_ATTENDEE_STATUS = {
    "accepted": AttendeeStatus.ACCEPTED,
    "declined": AttendeeStatus.DECLINED,
    "tentative": AttendeeStatus.TENTATIVE,
    "none": AttendeeStatus.NEEDS_ACTION,
    "notResponded": AttendeeStatus.NEEDS_ACTION,
}

_MS_SENSITIVITY_TO_VISIBILITY = {
    "normal": EventVisibility.DEFAULT,
    "personal": EventVisibility.PRIVATE,
    "private": EventVisibility.PRIVATE,
    "confidential": EventVisibility.CONFIDENTIAL,
}

_CANONICAL_VISIBILITY_TO_MS = {
    EventVisibility.DEFAULT: "normal",
    EventVisibility.PUBLIC: "normal",
    EventVisibility.PRIVATE: "private",
    EventVisibility.CONFIDENTIAL: "confidential",
}


def _serialize_recurrence(recurrence: Recurrence) -> dict[str, Any]:
    if recurrence.provider_data:
        return dict(recurrence.provider_data)
    raise ValueError(
        "Microsoft recurrence requires provider_data in Graph recurrence shape (pattern/range)."
    )


def _serialize_conference_data(conference_data: ConferenceData) -> dict[str, Any]:
    body: dict[str, Any] = {"isOnlineMeeting": True}
    provider_data = conference_data.provider_data or {}
    body["onlineMeetingProvider"] = provider_data.get("onlineMeetingProvider", "teamsForBusiness")
    return body


def _serialize_reminders(reminders: Reminder) -> dict[str, Any]:
    if reminders.use_default:
        return {"isReminderOn": True}
    if reminders.overrides:
        return {
            "isReminderOn": True,
            "reminderMinutesBeforeStart": max(0, reminders.overrides[0].minutes_before),
        }
    return {"isReminderOn": False}


# --------------------------------------------------------------------------- #
# Public mappers                                                               #
# --------------------------------------------------------------------------- #


def to_calendar_event(raw: dict, calendar_id: str) -> CalendarEvent:
    """Map a raw Microsoft Graph event dict to a canonical CalendarEvent."""
    start_obj = raw.get("start", {})
    end_obj = raw.get("end", {})
    start = _parse_ms_datetime(start_obj) or datetime.now(tz=timezone.utc)
    end = _parse_ms_datetime(end_obj) or datetime.now(tz=timezone.utc)
    all_day = raw.get("isAllDay", False)
    is_cancelled = bool(raw.get("isCancelled"))

    organizer_raw = raw.get("organizer", {}).get("emailAddress", {})
    organizer = None
    if organizer_raw:
        organizer = Organizer(
            email=organizer_raw.get("address", ""),
            display_name=organizer_raw.get("name"),
        )

    attendees = [
        Attendee(
            email=att.get("emailAddress", {}).get("address", ""),
            display_name=att.get("emailAddress", {}).get("name"),
            status=_MS_ATTENDEE_STATUS.get(
                att.get("status", {}).get("response", "none"),
                AttendeeStatus.NEEDS_ACTION,
            ),
        )
        for att in raw.get("attendees", [])
    ]

    recurrence = None
    if raw.get("recurrence"):
        recurrence = Recurrence(provider_data=raw["recurrence"])

    conference_data = None
    online_meeting = raw.get("onlineMeeting")
    if online_meeting and online_meeting.get("joinUrl"):
        conference_data = ConferenceData(
            join_url=online_meeting["joinUrl"],
            entry_points=[
                ConferenceEntryPoint(
                    entry_point_type="video",
                    uri=online_meeting["joinUrl"],
                )
            ],
            provider_data=online_meeting,
        )

    reminders = None
    if raw.get("isReminderOn") is not None:
        is_reminder_on = bool(raw.get("isReminderOn"))
        reminder_minutes = raw.get("reminderMinutesBeforeStart")
        overrides: list[ReminderOverride] = []
        if is_reminder_on and reminder_minutes is not None:
            overrides.append(ReminderOverride(method="popup", minutes_before=int(reminder_minutes)))
        reminders = Reminder(
            use_default=is_reminder_on and reminder_minutes is None, overrides=overrides
        )

    created_at = None
    if raw.get("createdDateTime"):
        with contextlib.suppress(Exception):
            created_at = datetime.fromisoformat(raw["createdDateTime"].replace("Z", "+00:00"))

    updated_at = None
    if raw.get("lastModifiedDateTime"):
        with contextlib.suppress(Exception):
            updated_at = datetime.fromisoformat(raw["lastModifiedDateTime"].replace("Z", "+00:00"))

    _MAPPED_KEYS = frozenset(
        {
            "id",
            "subject",
            "body",
            "location",
            "showAs",
            "start",
            "end",
            "isAllDay",
            "isCancelled",
            "organizer",
            "attendees",
            "recurrence",
            "onlineMeeting",
            "sensitivity",
            "isReminderOn",
            "reminderMinutesBeforeStart",
            "createdDateTime",
            "lastModifiedDateTime",
            "webLink",
            "iCalUId",
        }
    )
    return CalendarEvent(
        event_id=raw["id"],
        calendar_id=calendar_id,
        summary=raw.get("subject"),
        description=_extract_body_content(raw.get("body")),
        location=raw.get("location", {}).get("displayName") if raw.get("location") else None,
        status=(
            EventStatus.CANCELLED
            if is_cancelled
            else _MS_STATUS.get(raw.get("showAs", "busy"), EventStatus.CONFIRMED)
        ),
        visibility=_MS_SENSITIVITY_TO_VISIBILITY.get(
            raw.get("sensitivity", "normal"), EventVisibility.DEFAULT
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
        html_link=raw.get("webLink"),
        ical_uid=raw.get("iCalUId"),
        etag=raw.get("@odata.etag"),
        provider_data={k: v for k, v in raw.items() if k not in _MAPPED_KEYS},
    )


def from_calendar_event(event: CalendarEvent) -> dict[str, Any]:
    """Map a canonical CalendarEvent to a Microsoft Graph API event dict."""
    body: dict[str, Any] = {
        "subject": event.summary,
        "start": _format_ms_datetime(event.start, event.timezone),
        "end": _format_ms_datetime(event.end, event.timezone),
        "isAllDay": event.all_day,
    }
    if event.description is not None:
        body["body"] = {"contentType": "text", "content": event.description}
    if event.location is not None:
        body["location"] = {"displayName": event.location}
    if event.status and event.status != EventStatus.UNKNOWN:
        body["showAs"] = _CANONICAL_STATUS_TO_MS.get(event.status, "busy")
    if event.visibility:
        body["sensitivity"] = _CANONICAL_VISIBILITY_TO_MS.get(event.visibility, "normal")
    if event.attendees:
        body["attendees"] = [
            {
                "emailAddress": {"address": a.email, "name": a.display_name or ""},
                "type": "required",
            }
            for a in event.attendees
        ]
    if event.recurrence:
        body["recurrence"] = _serialize_recurrence(event.recurrence)
    if event.conference_data:
        body.update(_serialize_conference_data(event.conference_data))
    if event.reminders:
        body.update(_serialize_reminders(event.reminders))
    return body


def to_calendar(raw: dict) -> Calendar:
    """Map a raw Microsoft Graph calendar object to a canonical Calendar."""
    _MAPPED_KEYS = frozenset(
        {
            "id",
            "name",
            "description",
            "timeZone",
            "isDefaultCalendar",
            "canEdit",
            "hexColor",
        }
    )
    return Calendar(
        calendar_id=raw["id"],
        summary=raw.get("name", ""),
        description=raw.get("description"),
        timezone=raw.get("timeZone"),
        is_primary=raw.get("isDefaultCalendar", False),
        is_read_only=not raw.get("canEdit", True),
        background_color=raw.get("hexColor"),
        provider_data={k: v for k, v in raw.items() if k not in _MAPPED_KEYS},
    )
