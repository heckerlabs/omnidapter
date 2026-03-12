"""
Unit tests for omnidapter.providers.caldav.mappers.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from omnidapter.providers.caldav import mappers
from omnidapter.services.calendar.models import (
    Attendee,
    CalendarEvent,
    EventStatus,
    Recurrence,
)
from omnidapter.services.calendar.requests import CreateCalendarRequest, UpdateCalendarRequest

# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

_SIMPLE_ICAL = "\r\n".join(
    [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "BEGIN:VEVENT",
        "UID:test-uid-123",
        "DTSTART;VALUE=DATE-TIME:20240615T100000Z",
        "DTEND;VALUE=DATE-TIME:20240615T110000Z",
        "SUMMARY:Hello World",
        "DESCRIPTION:A test event",
        "LOCATION:Somewhere",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
)

_ALL_DAY_ICAL = "\r\n".join(
    [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "BEGIN:VEVENT",
        "UID:all-day-uid",
        "DTSTART;VALUE=DATE:20240615",
        "DTEND;VALUE=DATE:20240616",
        "SUMMARY:All Day",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
)


def _make_event(**kwargs: Any) -> CalendarEvent:
    defaults: dict[str, Any] = dict(
        event_id="test-uid-123",
        calendar_id="cal-1",
        summary="Hello World",
        start=datetime(2024, 6, 15, 10, 0, tzinfo=timezone.utc),
        end=datetime(2024, 6, 15, 11, 0, tzinfo=timezone.utc),
    )
    defaults.update(kwargs)
    return CalendarEvent(**defaults)


# --------------------------------------------------------------------------- #
# to_calendar_event                                                            #
# --------------------------------------------------------------------------- #


class TestToCalendarEvent:
    def test_basic_fields(self):
        event = mappers.to_calendar_event(_SIMPLE_ICAL, "cal-1")
        assert event is not None
        assert event.event_id == "test-uid-123"
        assert event.calendar_id == "cal-1"
        assert event.summary == "Hello World"
        assert event.description == "A test event"
        assert event.location == "Somewhere"

    def test_timed_event_datetime(self):
        event = mappers.to_calendar_event(_SIMPLE_ICAL, "c")
        assert event is not None
        assert isinstance(event.start, datetime)
        assert event.all_day is False

    def test_all_day_event_date(self):
        event = mappers.to_calendar_event(_ALL_DAY_ICAL, "c")
        assert event is not None
        assert isinstance(event.start, date)
        assert not isinstance(event.start, datetime)
        assert event.all_day is True

    def test_returns_none_when_no_vevent(self):
        result = mappers.to_calendar_event("BEGIN:VCALENDAR\r\nEND:VCALENDAR", "c")
        assert result is None

    def test_uid_used_as_event_id(self):
        event = mappers.to_calendar_event(_SIMPLE_ICAL, "c")
        assert event is not None
        assert event.event_id == "test-uid-123"
        assert event.ical_uid == "test-uid-123"

    def test_uid_generated_when_missing(self):
        ical = "\r\n".join(
            [
                "BEGIN:VCALENDAR",
                "BEGIN:VEVENT",
                "DTSTART;VALUE=DATE-TIME:20240615T100000Z",
                "DTEND;VALUE=DATE-TIME:20240615T110000Z",
                "SUMMARY:No UID",
                "END:VEVENT",
                "END:VCALENDAR",
            ]
        )
        event = mappers.to_calendar_event(ical, "c")
        assert event is not None
        assert event.event_id  # generated uid is non-empty

    def test_status_confirmed(self):
        ical = "\r\n".join(
            [
                "BEGIN:VCALENDAR",
                "BEGIN:VEVENT",
                "UID:x",
                "DTSTART;VALUE=DATE-TIME:20240615T100000Z",
                "DTEND;VALUE=DATE-TIME:20240615T110000Z",
                "STATUS:CONFIRMED",
                "END:VEVENT",
                "END:VCALENDAR",
            ]
        )
        event = mappers.to_calendar_event(ical, "c")
        assert event is not None
        assert event.status == EventStatus.CONFIRMED

    def test_status_cancelled(self):
        ical = "\r\n".join(
            [
                "BEGIN:VCALENDAR",
                "BEGIN:VEVENT",
                "UID:x",
                "DTSTART;VALUE=DATE-TIME:20240615T100000Z",
                "DTEND;VALUE=DATE-TIME:20240615T110000Z",
                "STATUS:CANCELLED",
                "END:VEVENT",
                "END:VCALENDAR",
            ]
        )
        event = mappers.to_calendar_event(ical, "c")
        assert event is not None
        assert event.status == EventStatus.CANCELLED

    def test_attendees_parsed(self):
        ical = "\r\n".join(
            [
                "BEGIN:VCALENDAR",
                "BEGIN:VEVENT",
                "UID:x",
                "DTSTART;VALUE=DATE-TIME:20240615T100000Z",
                "DTEND;VALUE=DATE-TIME:20240615T110000Z",
                "ATTENDEE;CN=Alice:mailto:alice@example.com",
                "ATTENDEE;CN=Bob:mailto:bob@example.com",
                "END:VEVENT",
                "END:VCALENDAR",
            ]
        )
        event = mappers.to_calendar_event(ical, "c")
        assert event is not None
        emails = {a.email for a in event.attendees}
        assert "alice@example.com" in emails
        assert "bob@example.com" in emails

    def test_rrule_captured(self):
        ical = "\r\n".join(
            [
                "BEGIN:VCALENDAR",
                "BEGIN:VEVENT",
                "UID:x",
                "DTSTART;VALUE=DATE-TIME:20240615T100000Z",
                "DTEND;VALUE=DATE-TIME:20240615T110000Z",
                "RRULE:FREQ=WEEKLY;COUNT=4",
                "END:VEVENT",
                "END:VCALENDAR",
            ]
        )
        event = mappers.to_calendar_event(ical, "c")
        assert event is not None
        assert event.recurrence is not None
        assert any("RRULE" in r for r in event.recurrence.rules)

    def test_raw_props_in_provider_data(self):
        event = mappers.to_calendar_event(_SIMPLE_ICAL, "c")
        assert event is not None
        assert event.provider_data is not None
        assert "raw_props" in event.provider_data

    def test_created_last_modified_timestamps(self):
        ical = "\r\n".join(
            [
                "BEGIN:VCALENDAR",
                "BEGIN:VEVENT",
                "UID:x",
                "DTSTART;VALUE=DATE-TIME:20240615T100000Z",
                "DTEND;VALUE=DATE-TIME:20240615T110000Z",
                "CREATED:20240101T000000Z",
                "LAST-MODIFIED:20240601T120000Z",
                "END:VEVENT",
                "END:VCALENDAR",
            ]
        )
        event = mappers.to_calendar_event(ical, "c")
        assert event is not None
        assert event.created_at is not None
        assert event.updated_at is not None


# --------------------------------------------------------------------------- #
# from_calendar_event                                                          #
# --------------------------------------------------------------------------- #


class TestFromCalendarEvent:
    def test_returns_string(self):
        event = _make_event()
        result = mappers.from_calendar_event(event)
        assert isinstance(result, str)

    def test_vcalendar_structure(self):
        event = _make_event()
        result = mappers.from_calendar_event(event)
        assert "BEGIN:VCALENDAR" in result
        assert "BEGIN:VEVENT" in result
        assert "END:VEVENT" in result
        assert "END:VCALENDAR" in result

    def test_uid_in_output(self):
        event = _make_event()
        result = mappers.from_calendar_event(event)
        assert "UID:test-uid-123" in result

    def test_summary_in_output(self):
        event = _make_event()
        result = mappers.from_calendar_event(event)
        assert "SUMMARY:Hello World" in result

    def test_description_and_location(self):
        event = _make_event(description="My desc", location="NYC")
        result = mappers.from_calendar_event(event)
        assert "DESCRIPTION:My desc" in result
        assert "LOCATION:NYC" in result

    def test_timed_event_date_time(self):
        event = _make_event()
        result = mappers.from_calendar_event(event)
        assert "DATE-TIME" in result
        assert "T100000Z" in result

    def test_all_day_event_date_only(self):
        event = _make_event(
            start=date(2024, 6, 15),
            end=date(2024, 6, 16),
            all_day=True,
        )
        result = mappers.from_calendar_event(event)
        assert "VALUE=DATE:20240615" in result
        assert "DATE-TIME" not in result

    def test_attendees_in_output(self):
        event = _make_event(
            attendees=[
                Attendee(email="alice@example.com", display_name="Alice"),
                Attendee(email="bob@example.com"),
            ]
        )
        result = mappers.from_calendar_event(event)
        assert "mailto:alice@example.com" in result
        assert "CN=Alice" in result
        assert "mailto:bob@example.com" in result

    def test_status_tentative_in_output(self):
        event = _make_event(status=EventStatus.TENTATIVE)
        result = mappers.from_calendar_event(event)
        assert "STATUS:TENTATIVE" in result

    def test_confirmed_status_not_emitted(self):
        # CONFIRMED is default; we don't emit it to keep output clean
        event = _make_event(status=EventStatus.CONFIRMED)
        result = mappers.from_calendar_event(event)
        assert "STATUS:CONFIRMED" not in result

    def test_rrule_in_output(self):
        event = _make_event(recurrence=Recurrence(rules=["RRULE:FREQ=WEEKLY;COUNT=4"]))
        result = mappers.from_calendar_event(event)
        assert "RRULE:FREQ=WEEKLY;COUNT=4" in result

    def test_roundtrip_basic(self):
        event = _make_event(description="round-trip desc", location="round-trip loc")
        ical_text = mappers.from_calendar_event(event)
        recovered = mappers.to_calendar_event(ical_text, "cal-1")
        assert recovered is not None
        assert recovered.event_id == event.event_id
        assert recovered.summary == event.summary
        assert recovered.description == event.description
        assert recovered.location == event.location


class TestCalendarCrudMappers:
    def test_from_create_calendar_request(self):
        req = CreateCalendarRequest(summary="Team", description="Desc", timezone="UTC")
        props = mappers.from_create_calendar_request(req)
        assert props["displayname"] == "Team"
        assert props["calendar-description"] == "Desc"
        assert props["calendar-timezone"] == "UTC"

    def test_from_update_calendar_request(self):
        req = UpdateCalendarRequest(calendar_id="/cal/1/", summary="Renamed")
        props = mappers.from_update_calendar_request(req)
        assert props == {"displayname": "Renamed"}

    def test_slugify_calendar_name(self):
        assert mappers.slugify_calendar_name("Team Ops 2026!") == "team-ops-2026"

    def test_parse_collection_href(self):
        assert mappers.parse_collection_href("https://dav.example.com/cal/a/") == "/cal/a/"
        assert mappers.parse_collection_href("/cal/a/") == "/cal/a/"
