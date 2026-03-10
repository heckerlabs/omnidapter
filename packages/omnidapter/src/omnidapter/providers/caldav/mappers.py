"""
Mappers between iCalendar (CalDAV) format and canonical types.

CalDAV uses iCalendar text rather than JSON, so:
  to_calendar_event(ical_text, calendar_id) -> CalendarEvent
  from_calendar_event(event) -> str  (VCALENDAR iCalendar text)
"""
from __future__ import annotations

import secrets
from datetime import date, datetime, timezone

from omnidapter.services.calendar.models import (
    Attendee,
    CalendarEvent,
    EventStatus,
    Recurrence,
)


# --------------------------------------------------------------------------- #
# Private helpers                                                              #
# --------------------------------------------------------------------------- #

def _parse_ical_datetime(value: str) -> datetime | date:
    value = value.strip()
    if "T" in value:
        value = value.rstrip("Z")
        try:
            return datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return datetime.now(tz=timezone.utc)
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:8]))
    except (ValueError, IndexError):
        return date.today()


def _format_ical_datetime(dt: datetime | date, all_day: bool = False) -> str:
    if all_day or (isinstance(dt, date) and not isinstance(dt, datetime)):
        d = dt.date() if isinstance(dt, datetime) else dt
        return d.strftime("%Y%m%d")
    if isinstance(dt, datetime):
        return dt.strftime("%Y%m%dT%H%M%SZ")
    return str(dt)


_ICAL_STATUS = {
    "CONFIRMED": EventStatus.CONFIRMED,
    "TENTATIVE": EventStatus.TENTATIVE,
    "CANCELLED": EventStatus.CANCELLED,
}
_CANONICAL_STATUS_TO_ICAL = {v: k for k, v in _ICAL_STATUS.items()}


# --------------------------------------------------------------------------- #
# Public mappers                                                               #
# --------------------------------------------------------------------------- #

def to_calendar_event(ical_text: str, calendar_id: str) -> CalendarEvent | None:
    """Parse a VEVENT from an iCalendar string into a canonical CalendarEvent.

    Returns None if no VEVENT block is found.
    """
    lines = ical_text.replace("\r\n ", "").replace("\n ", "").splitlines()
    props: dict[str, str] = {}
    in_vevent = False
    attendees_raw: list[str] = []
    rrules: list[str] = []

    for line in lines:
        if line.strip() == "BEGIN:VEVENT":
            in_vevent = True
            continue
        if line.strip() == "END:VEVENT":
            break
        if not in_vevent or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key_base = key.split(";")[0].upper()
        if key_base == "ATTENDEE":
            attendees_raw.append(value)
        elif key_base in ("RRULE", "EXRULE", "RDATE", "EXDATE"):
            rrules.append(line)
        else:
            props[key_base] = value

    if not props and not in_vevent:
        return None

    uid = props.get("UID") or secrets.token_urlsafe(8)
    dtstart_str = props.get("DTSTART", "")
    dtend_str = props.get("DTEND", "")
    all_day = "T" not in dtstart_str

    try:
        start = _parse_ical_datetime(dtstart_str)
    except Exception:
        start = datetime.now(tz=timezone.utc)
    try:
        end = _parse_ical_datetime(dtend_str)
    except Exception:
        end = datetime.now(tz=timezone.utc)

    status = _ICAL_STATUS.get(props.get("STATUS", "CONFIRMED").upper(), EventStatus.CONFIRMED)

    attendees = [
        Attendee(email=v.replace("mailto:", "").strip())
        for v in attendees_raw
    ]

    recurrence = Recurrence(rules=rrules) if rrules else None

    created_at = None
    if props.get("CREATED"):
        try:
            v = _parse_ical_datetime(props["CREATED"])
            created_at = v if isinstance(v, datetime) else None
        except Exception:
            pass

    updated_at = None
    if props.get("LAST-MODIFIED"):
        try:
            v = _parse_ical_datetime(props["LAST-MODIFIED"])
            updated_at = v if isinstance(v, datetime) else None
        except Exception:
            pass

    return CalendarEvent(
        event_id=uid,
        calendar_id=calendar_id,
        summary=props.get("SUMMARY") or None,
        description=props.get("DESCRIPTION"),
        location=props.get("LOCATION"),
        status=status,
        start=start,
        end=end,
        all_day=all_day,
        attendees=attendees,
        recurrence=recurrence,
        created_at=created_at,
        updated_at=updated_at,
        ical_uid=uid,
        provider_data={"raw_props": props},
    )


def from_calendar_event(event: CalendarEvent) -> str:
    """Map a canonical CalendarEvent to a VCALENDAR iCalendar string.

    ``event.event_id`` is used as the VEVENT UID and must be set before calling.
    """
    dtstart = _format_ical_datetime(event.start, event.all_day)
    dtend = _format_ical_datetime(event.end, event.all_day)
    date_type = "DATE" if event.all_day else "DATE-TIME"

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Omnidapter//Omnidapter//EN",
        "BEGIN:VEVENT",
        f"UID:{event.event_id}",
        f"DTSTART;VALUE={date_type}:{dtstart}",
        f"DTEND;VALUE={date_type}:{dtend}",
        f"SUMMARY:{event.summary or ''}",
    ]
    if event.description:
        lines.append(f"DESCRIPTION:{event.description}")
    if event.location:
        lines.append(f"LOCATION:{event.location}")
    if event.status and event.status in _CANONICAL_STATUS_TO_ICAL:
        ical_status = _CANONICAL_STATUS_TO_ICAL[event.status]
        if ical_status != "CONFIRMED":
            lines.append(f"STATUS:{ical_status}")
    for att in event.attendees:
        cn = att.display_name or att.email
        lines.append(f"ATTENDEE;CN={cn}:mailto:{att.email}")
    if event.recurrence:
        lines.extend(event.recurrence.rules)
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(lines)
