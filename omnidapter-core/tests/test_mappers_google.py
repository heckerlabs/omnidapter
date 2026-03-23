"""
Unit tests for omnidapter.providers.google.mappers.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest
from omnidapter.providers.google import mappers
from omnidapter.services.calendar.models import (
    Attendee,
    AttendeeStatus,
    CalendarEvent,
    ConferenceData,
    EventStatus,
    EventVisibility,
    Recurrence,
    Reminder,
    ReminderOverride,
)
from omnidapter.services.calendar.requests import CreateCalendarRequest, UpdateCalendarRequest

# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _make_raw(overrides: dict | None = None) -> dict:
    base = {
        "id": "evt-1",
        "summary": "Test event",
        "start": {"dateTime": "2024-06-15T10:00:00Z", "timeZone": "UTC"},
        "end": {"dateTime": "2024-06-15T11:00:00Z", "timeZone": "UTC"},
        "status": "confirmed",
        "visibility": "default",
    }
    if overrides:
        base.update(overrides)
    return base


def _make_event(**kwargs: Any) -> CalendarEvent:
    defaults: dict[str, Any] = dict(
        event_id="evt-1",
        calendar_id="cal-1",
        summary="Test event",
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
        raw = _make_raw({"description": "hello", "location": "Mars"})
        event = mappers.to_calendar_event(raw, "cal-1")
        assert event.event_id == "evt-1"
        assert event.calendar_id == "cal-1"
        assert event.summary == "Test event"
        assert event.description == "hello"
        assert event.location == "Mars"

    def test_status_mapping(self):
        for api_status, expected in [
            ("confirmed", EventStatus.CONFIRMED),
            ("tentative", EventStatus.TENTATIVE),
            ("cancelled", EventStatus.CANCELLED),
        ]:
            event = mappers.to_calendar_event(_make_raw({"status": api_status}), "c")
            assert event.status == expected

    def test_visibility_mapping(self):
        for api_vis, expected in [
            ("public", EventVisibility.PUBLIC),
            ("private", EventVisibility.PRIVATE),
            ("confidential", EventVisibility.CONFIDENTIAL),
            ("default", EventVisibility.DEFAULT),
        ]:
            event = mappers.to_calendar_event(_make_raw({"visibility": api_vis}), "c")
            assert event.visibility == expected

    def test_timed_event_parses_datetime(self):
        event = mappers.to_calendar_event(_make_raw(), "c")
        assert isinstance(event.start, datetime)
        assert isinstance(event.end, datetime)
        assert event.all_day is False

    def test_all_day_event_parses_date(self):
        raw = _make_raw(
            {
                "start": {"date": "2024-06-15"},
                "end": {"date": "2024-06-16"},
            }
        )
        event = mappers.to_calendar_event(raw, "c")
        assert isinstance(event.start, date)
        assert not isinstance(event.start, datetime)
        assert event.all_day is True

    def test_organizer_mapped(self):
        raw = _make_raw(
            {"organizer": {"email": "boss@example.com", "displayName": "Boss", "self": True}}
        )
        event = mappers.to_calendar_event(raw, "c")
        assert event.organizer is not None
        assert event.organizer.email == "boss@example.com"
        assert event.organizer.display_name == "Boss"
        assert event.organizer.is_self is True

    def test_attendees_mapped(self):
        raw = _make_raw(
            {
                "attendees": [
                    {"email": "a@x.com", "displayName": "A", "responseStatus": "accepted"},
                    {"email": "b@x.com", "responseStatus": "declined"},
                ]
            }
        )
        event = mappers.to_calendar_event(raw, "c")
        assert len(event.attendees) == 2
        assert event.attendees[0].email == "a@x.com"
        assert event.attendees[0].status == AttendeeStatus.ACCEPTED
        assert event.attendees[1].status == AttendeeStatus.DECLINED

    def test_attendee_unknown_status(self):
        raw = _make_raw({"attendees": [{"email": "x@y.com", "responseStatus": "unknown_value"}]})
        event = mappers.to_calendar_event(raw, "c")
        assert event.attendees[0].status == AttendeeStatus.UNKNOWN

    def test_recurrence_rules_mapped(self):
        raw = _make_raw({"recurrence": ["RRULE:FREQ=WEEKLY;COUNT=4"]})
        event = mappers.to_calendar_event(raw, "c")
        assert event.recurrence is not None
        assert "RRULE:FREQ=WEEKLY;COUNT=4" in event.recurrence.rules

    def test_recurring_event_id(self):
        raw = _make_raw({"recurringEventId": "parent-123"})
        event = mappers.to_calendar_event(raw, "c")
        assert event.recurrence is not None
        assert event.recurrence.recurring_event_id == "parent-123"

    def test_conference_data_mapped(self):
        raw = _make_raw(
            {
                "conferenceData": {
                    "conferenceId": "conf-1",
                    "conferenceSolution": {"name": "Google Meet"},
                    "entryPoints": [
                        {"entryPointType": "video", "uri": "https://meet.google.com/abc"},
                    ],
                }
            }
        )
        event = mappers.to_calendar_event(raw, "c")
        assert event.conference_data is not None
        assert event.conference_data.conference_id == "conf-1"
        assert event.conference_data.conference_solution_name == "Google Meet"
        assert event.conference_data.join_url == "https://meet.google.com/abc"

    def test_reminders_mapped(self):
        raw = _make_raw(
            {
                "reminders": {
                    "useDefault": False,
                    "overrides": [{"method": "popup", "minutes": 20}],
                }
            }
        )
        event = mappers.to_calendar_event(raw, "c")
        assert event.reminders is not None
        assert event.reminders.use_default is False
        assert event.reminders.overrides
        assert event.reminders.overrides[0].method == "popup"
        assert event.reminders.overrides[0].minutes_before == 20

    def test_created_updated_timestamps(self):
        raw = _make_raw(
            {
                "created": "2024-01-01T00:00:00Z",
                "updated": "2024-06-01T12:00:00Z",
            }
        )
        event = mappers.to_calendar_event(raw, "c")
        assert event.created_at is not None
        assert event.updated_at is not None
        assert event.created_at.year == 2024

    def test_extra_keys_go_to_provider_data(self):
        raw = _make_raw({"extendedProperties": {"private": {"foo": "bar"}}})
        event = mappers.to_calendar_event(raw, "c")
        assert event.provider_data is not None
        assert "extendedProperties" in event.provider_data

    def test_mapped_keys_not_in_provider_data(self):
        raw = _make_raw()
        event = mappers.to_calendar_event(raw, "c")
        # Core fields must not bleed into provider_data
        assert "id" not in (event.provider_data or {})
        assert "summary" not in (event.provider_data or {})

    def test_invalid_time_raises(self):
        raw = _make_raw({"start": {}, "end": {}})
        with pytest.raises(ValueError):
            mappers.to_calendar_event(raw, "c")


# --------------------------------------------------------------------------- #
# from_calendar_event                                                          #
# --------------------------------------------------------------------------- #


class TestFromCalendarEvent:
    def test_basic_fields(self):
        event = _make_event()
        body = mappers.from_calendar_event(event)
        assert body["summary"] == "Test event"
        assert "start" in body
        assert "end" in body

    def test_timed_event_uses_datetime_key(self):
        event = _make_event()
        body = mappers.from_calendar_event(event)
        assert "dateTime" in body["start"]
        assert "date" not in body["start"]

    def test_all_day_uses_date_key(self):
        event = _make_event(
            start=date(2024, 6, 15),
            end=date(2024, 6, 16),
            all_day=True,
        )
        body = mappers.from_calendar_event(event)
        assert "date" in body["start"]
        assert "dateTime" not in body["start"]

    def test_optional_fields_omitted_when_none(self):
        event = _make_event()
        body = mappers.from_calendar_event(event)
        assert "description" not in body
        assert "location" not in body

    def test_optional_fields_included_when_set(self):
        event = _make_event(description="desc", location="loc")
        body = mappers.from_calendar_event(event)
        assert body["description"] == "desc"
        assert body["location"] == "loc"

    def test_status_mapped(self):
        event = _make_event(status=EventStatus.TENTATIVE)
        body = mappers.from_calendar_event(event)
        assert body["status"] == "tentative"

    def test_status_unknown_not_emitted(self):
        event = _make_event(status=EventStatus.UNKNOWN)
        body = mappers.from_calendar_event(event)
        assert "status" not in body

    def test_attendees_mapped(self):
        event = _make_event(
            attendees=[
                Attendee(email="a@x.com", display_name="A", optional=True),
            ]
        )
        body = mappers.from_calendar_event(event)
        assert body["attendees"][0]["email"] == "a@x.com"
        assert body["attendees"][0]["optional"] is True

    def test_recurrence_rules_emitted(self):
        event = _make_event(recurrence=Recurrence(rules=["RRULE:FREQ=DAILY"]))
        body = mappers.from_calendar_event(event)
        assert body["recurrence"] == ["RRULE:FREQ=DAILY"]

    def test_timezone_added_to_start_end(self):
        event = _make_event(timezone="America/New_York")
        body = mappers.from_calendar_event(event)
        assert body["start"]["timeZone"] == "America/New_York"
        assert body["end"]["timeZone"] == "America/New_York"

    def test_recurrence_without_explicit_timezone_infers_utc(self):
        event = _make_event(
            timezone=None,
            recurrence=Recurrence(rules=["RRULE:FREQ=DAILY;COUNT=2"]),
        )
        body = mappers.from_calendar_event(event)
        assert body["start"]["timeZone"] == "UTC"
        assert body["end"]["timeZone"] == "UTC"

    def test_recurrence_without_explicit_timezone_uses_iana_zoneinfo_key(self):
        try:
            tz = ZoneInfo("America/New_York")
        except ZoneInfoNotFoundError:
            pytest.skip("IANA tzdata not available in runtime environment")

        event = _make_event(
            start=datetime(2024, 6, 15, 10, 0, tzinfo=tz),
            end=datetime(2024, 6, 15, 11, 0, tzinfo=tz),
            timezone=None,
            recurrence=Recurrence(rules=["RRULE:FREQ=DAILY;COUNT=2"]),
        )
        body = mappers.from_calendar_event(event)
        assert body["start"]["timeZone"] == "America/New_York"
        assert body["end"]["timeZone"] == "America/New_York"

    def test_recurrence_without_explicit_timezone_falls_back_to_utc_for_offset_tz(self):
        fixed_offset_tz = timezone(timedelta(hours=-5))
        event = _make_event(
            start=datetime(2024, 6, 15, 10, 0, tzinfo=fixed_offset_tz),
            end=datetime(2024, 6, 15, 11, 0, tzinfo=fixed_offset_tz),
            timezone=None,
            recurrence=Recurrence(rules=["RRULE:FREQ=DAILY;COUNT=2"]),
        )
        body = mappers.from_calendar_event(event)
        assert body["start"]["timeZone"] == "UTC"
        assert body["end"]["timeZone"] == "UTC"

    def test_conference_data_generates_create_request(self):
        event = _make_event(conference_data=ConferenceData())
        body = mappers.from_calendar_event(event)
        assert "conferenceData" in body
        assert "createRequest" in body["conferenceData"]
        assert (
            body["conferenceData"]["createRequest"]["conferenceSolutionKey"]["type"]
            == "hangoutsMeet"
        )

    def test_conference_data_provider_data_preserved(self):
        event = _make_event(
            conference_data=ConferenceData(
                provider_data={"createRequest": {"requestId": "abc-123"}}
            )
        )
        body = mappers.from_calendar_event(event)
        assert body["conferenceData"]["createRequest"]["requestId"] == "abc-123"

    def test_reminders_serialized(self):
        event = _make_event(
            reminders=Reminder(
                use_default=False,
                overrides=[ReminderOverride(method="popup", minutes_before=15)],
            )
        )
        body = mappers.from_calendar_event(event)
        assert body["reminders"]["useDefault"] is False
        assert body["reminders"]["overrides"][0]["method"] == "popup"
        assert body["reminders"]["overrides"][0]["minutes"] == 15


# --------------------------------------------------------------------------- #
# to_calendar                                                                  #
# --------------------------------------------------------------------------- #


class TestToCalendar:
    def test_basic_fields(self):
        raw = {
            "id": "cal-1",
            "summary": "My Calendar",
            "description": "A calendar",
            "timeZone": "UTC",
            "primary": True,
            "accessRole": "owner",
            "backgroundColor": "#ff0000",
            "foregroundColor": "#ffffff",
        }
        cal = mappers.to_calendar(raw)
        assert cal.calendar_id == "cal-1"
        assert cal.summary == "My Calendar"
        assert cal.is_primary is True
        assert cal.is_read_only is False
        assert cal.background_color == "#ff0000"

    def test_reader_access_role_is_read_only(self):
        cal = mappers.to_calendar({"id": "c", "summary": "s", "accessRole": "reader"})
        assert cal.is_read_only is True

    def test_free_busy_reader_is_read_only(self):
        cal = mappers.to_calendar({"id": "c", "summary": "s", "accessRole": "freeBusyReader"})
        assert cal.is_read_only is True

    def test_extra_keys_in_provider_data(self):
        raw = {"id": "c", "summary": "s", "customField": "custom"}
        cal = mappers.to_calendar(raw)
        assert cal.provider_data is not None
        assert "customField" in cal.provider_data

    def test_mapped_keys_not_in_provider_data(self):
        raw = {"id": "c", "summary": "s", "timeZone": "UTC"}
        cal = mappers.to_calendar(raw)
        assert "id" not in (cal.provider_data or {})
        assert "timeZone" not in (cal.provider_data or {})


class TestCalendarCrudMappers:
    def test_from_create_calendar_request(self):
        req = CreateCalendarRequest(
            summary="Team Calendar",
            description="Planning",
            timezone="UTC",
            background_color="#112233",
            foreground_color="#ffffff",
            extra={"selected": True},
        )
        body = mappers.from_create_calendar_request(req)
        assert body["summary"] == "Team Calendar"
        assert body["description"] == "Planning"
        assert body["timeZone"] == "UTC"
        assert body["backgroundColor"] == "#112233"
        assert body["foregroundColor"] == "#ffffff"
        assert body["selected"] is True

    def test_from_update_calendar_request_omits_none(self):
        req = UpdateCalendarRequest(calendar_id="cal-1", summary="Renamed")
        body = mappers.from_update_calendar_request(req)
        assert body == {"summary": "Renamed"}
