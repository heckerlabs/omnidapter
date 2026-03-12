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
    """Request model for creating a calendar event."""

    calendar_id: str
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
    """Request model for updating a calendar event."""

    calendar_id: str
    event_id: str
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
