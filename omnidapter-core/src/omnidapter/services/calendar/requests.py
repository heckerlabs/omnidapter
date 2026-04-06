"""
Request models for calendar service write operations.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel

from omnidapter.services.calendar.models import (
    Attendee,
    ConferenceData,
    EventStatus,
    Recurrence,
    Reminder,
)


class CreateEventRequest(BaseModel):
    """Request model for creating a calendar event.

    When used via the REST API, ``calendar_id`` is injected from the URL path
    parameter and must not be set in the request body.  When using the Python
    library directly, callers must supply a non-empty ``calendar_id``.
    """

    calendar_id: str = ""
    summary: str
    start: datetime | date
    end: datetime | date
    all_day: bool = False
    timezone: str | None = None
    description: str | None = None
    location: str | None = None
    attendees: list[Attendee] = []
    recurrence: Recurrence | None = None
    conference_data: ConferenceData | None = None
    reminders: Reminder | None = None
    visibility: str | None = None
    status: EventStatus | None = None
    extra: dict[str, Any] = {}  # Provider-specific extra fields


class UpdateEventRequest(BaseModel):
    """Request model for updating a calendar event.

    When used via the REST API, ``calendar_id`` and ``event_id`` are injected
    from URL path parameters.  When using the Python library directly, callers
    must supply non-empty values for both fields.
    """

    calendar_id: str = ""
    event_id: str = ""
    summary: str | None = None
    start: datetime | date | None = None
    end: datetime | date | None = None
    all_day: bool | None = None
    timezone: str | None = None
    description: str | None = None
    location: str | None = None
    attendees: list[Attendee] | None = None
    recurrence: Recurrence | None = None
    conference_data: ConferenceData | None = None
    reminders: Reminder | None = None
    visibility: str | None = None
    status: EventStatus | None = None
    extra: dict[str, Any] = {}  # Provider-specific extra fields


class GetAvailabilityRequest(BaseModel):
    """Request model for querying free/busy availability."""

    calendar_ids: list[str]
    time_min: datetime
    time_max: datetime
    timezone: str | None = None


class CreateCalendarRequest(BaseModel):
    """Request model for creating a calendar."""

    summary: str
    description: str | None = None
    timezone: str | None = None
    background_color: str | None = None
    foreground_color: str | None = None
    extra: dict[str, Any] = {}


class UpdateCalendarRequest(BaseModel):
    """Request model for updating a calendar.

    When used via the REST API, ``calendar_id`` is injected from the URL path
    parameter.  When using the Python library directly, callers must supply a
    non-empty ``calendar_id``.
    """

    calendar_id: str = ""
    summary: str | None = None
    description: str | None = None
    timezone: str | None = None
    background_color: str | None = None
    foreground_color: str | None = None
    extra: dict[str, Any] = {}
