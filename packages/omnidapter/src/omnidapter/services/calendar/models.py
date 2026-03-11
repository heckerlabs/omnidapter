"""
Normalized calendar domain models.

Common fields are first-class. Provider-specific or unmapped data goes into
`provider_data` (typed as dict[str, Any] | None, not covered by semver guarantees).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


class AttendeeStatus(str, Enum):
    ACCEPTED = "accepted"
    DECLINED = "declined"
    TENTATIVE = "tentative"
    NEEDS_ACTION = "needs_action"
    UNKNOWN = "unknown"


class EventStatus(str, Enum):
    CONFIRMED = "confirmed"
    TENTATIVE = "tentative"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class EventVisibility(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    CONFIDENTIAL = "confidential"
    DEFAULT = "default"


class ConferenceEntryPoint(BaseModel):
    """A single entry point for a conference (e.g., video URL, phone dial-in)."""

    entry_point_type: str  # "video", "phone", "sip", "more"
    uri: str
    label: str | None = None
    pin: str | None = None
    provider_data: dict[str, Any] | None = None


class ConferenceData(BaseModel):
    """Conference/video call information attached to an event."""

    conference_id: str | None = None
    conference_solution_name: str | None = None
    entry_points: list[ConferenceEntryPoint] = []
    join_url: str | None = None
    provider_data: dict[str, Any] | None = None


class ReminderOverride(BaseModel):
    """A single reminder override for an event."""

    method: str  # "email", "popup", "sms"
    minutes_before: int


class Reminder(BaseModel):
    """Reminder configuration for an event."""

    use_default: bool = False
    overrides: list[ReminderOverride] = []


class Recurrence(BaseModel):
    """Recurrence information for recurring events.

    `rules` contains RRULE/EXRULE/RDATE/EXDATE strings (RFC 5545 format).
    """

    rules: list[str] = []
    recurring_event_id: str | None = None
    original_start_time: datetime | date | None = None
    provider_data: dict[str, Any] | None = None


class Attendee(BaseModel):
    """An event attendee."""

    email: str
    display_name: str | None = None
    status: AttendeeStatus = AttendeeStatus.NEEDS_ACTION
    is_organizer: bool = False
    is_self: bool = False
    is_resource: bool = False
    optional: bool = False
    comment: str | None = None
    provider_data: dict[str, Any] | None = None


class Organizer(BaseModel):
    """Event organizer."""

    email: str
    display_name: str | None = None
    is_self: bool = False
    provider_data: dict[str, Any] | None = None


class CalendarEvent(BaseModel):
    """A normalized calendar event."""

    event_id: str
    calendar_id: str
    summary: str | None = None
    description: str | None = None
    location: str | None = None
    status: EventStatus = EventStatus.CONFIRMED
    visibility: EventVisibility = EventVisibility.DEFAULT

    # Time fields
    start: datetime | date  # datetime = timed event, date = all-day
    end: datetime | date
    all_day: bool = False
    timezone: str | None = None

    # Organizer / attendees
    organizer: Organizer | None = None
    attendees: list[Attendee] = []

    # Recurrence
    recurrence: Recurrence | None = None

    # Conference data
    conference_data: ConferenceData | None = None

    # Reminders
    reminders: Reminder | None = None

    # Metadata
    created_at: datetime | None = None
    updated_at: datetime | None = None
    html_link: str | None = None
    ical_uid: str | None = None
    etag: str | None = None
    sequence: int | None = None

    # Provider-specific escape hatch — not covered by semver
    provider_data: dict[str, Any] | None = None


class Calendar(BaseModel):
    """A normalized calendar."""

    calendar_id: str
    summary: str
    description: str | None = None
    timezone: str | None = None
    is_primary: bool = False
    is_read_only: bool = False
    background_color: str | None = None
    foreground_color: str | None = None
    provider_data: dict[str, Any] | None = None


class FreeBusyInterval(BaseModel):
    """A busy time interval."""

    start: datetime
    end: datetime
    provider_data: dict[str, Any] | None = None


class AvailabilityResponse(BaseModel):
    """Result of a free/busy availability query."""

    queried_calendars: list[str]
    time_min: datetime
    time_max: datetime
    busy_intervals: list[FreeBusyInterval] = []
    provider_data: dict[str, Any] | None = None
