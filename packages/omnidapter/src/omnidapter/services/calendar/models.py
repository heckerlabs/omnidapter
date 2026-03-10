from __future__ import annotations

from datetime import date as date_cls, datetime
from typing import Any

from pydantic import BaseModel, Field


class EventTime(BaseModel):
    date_time: datetime | None = None
    date: date_cls | None = None
    timezone: str | None = None


class EventAttendee(BaseModel):
    email: str
    display_name: str | None = None
    response_status: str | None = None


class Organizer(BaseModel):
    email: str | None = None
    display_name: str | None = None


class ConferenceData(BaseModel):
    uri: str | None = None
    conference_id: str | None = None
    provider: str | None = None


class ReminderData(BaseModel):
    use_default: bool = True
    minutes_before: list[int] = Field(default_factory=list)


class RecurrenceData(BaseModel):
    rrule: list[str] = Field(default_factory=list)


class Calendar(BaseModel):
    id: str
    summary: str
    timezone: str | None = None
    provider_data: dict[str, Any] | None = None


class Event(BaseModel):
    id: str
    calendar_id: str
    summary: str | None = None
    description: str | None = None
    location: str | None = None
    start: EventTime
    end: EventTime
    organizer: Organizer | None = None
    attendees: list[EventAttendee] = Field(default_factory=list)
    recurrence: RecurrenceData | None = None
    conference: ConferenceData | None = None
    reminders: ReminderData | None = None
    provider_data: dict[str, Any] | None = None


class FreeBusyInterval(BaseModel):
    start: datetime
    end: datetime


class AvailabilityResponse(BaseModel):
    calendar_id: str
    busy: list[FreeBusyInterval] = Field(default_factory=list)


class EventUpsertRequest(BaseModel):
    calendar_id: str
    summary: str
    start: EventTime
    end: EventTime
    attendees: list[EventAttendee] = Field(default_factory=list)
    provider_data: dict[str, Any] | None = None
