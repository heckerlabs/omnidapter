"""
Unit tests for omnidapter.providers.microsoft.mappers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from omnidapter.providers.microsoft import mappers
from omnidapter.services.calendar.models import (
    Attendee,
    AttendeeStatus,
    CalendarEvent,
    EventStatus,
)

# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _make_raw(overrides: dict | None = None) -> dict:
    base = {
        "id": "evt-ms-1",
        "subject": "MS Test Event",
        "start": {"dateTime": "2024-06-15T10:00:00", "timeZone": "UTC"},
        "end": {"dateTime": "2024-06-15T11:00:00", "timeZone": "UTC"},
        "isAllDay": False,
        "showAs": "normal",
    }
    if overrides:
        base.update(overrides)
    return base


def _make_event(**kwargs) -> CalendarEvent:
    defaults = dict(
        event_id="evt-ms-1",
        calendar_id="cal-1",
        summary="MS Test Event",
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
        raw = _make_raw(
            {
                "body": {"content": "hello"},
                "location": {"displayName": "Mars"},
            }
        )
        event = mappers.to_calendar_event(raw, "cal-1")
        assert event.event_id == "evt-ms-1"
        assert event.calendar_id == "cal-1"
        assert event.summary == "MS Test Event"
        assert event.description == "hello"
        assert event.location == "Mars"

    def test_timed_event(self):
        event = mappers.to_calendar_event(_make_raw(), "c")
        assert isinstance(event.start, datetime)
        assert event.all_day is False

    def test_datetime_utc_timezone(self):
        raw = _make_raw(
            {
                "start": {"dateTime": "2024-06-15T10:00:00", "timeZone": "UTC"},
                "end": {"dateTime": "2024-06-15T11:00:00", "timeZone": "UTC"},
            }
        )
        event = mappers.to_calendar_event(raw, "c")
        assert event.start.tzinfo is not None
        assert event.start.utcoffset().total_seconds() == 0

    def test_datetime_iana_timezone(self):
        raw = _make_raw(
            {
                "start": {"dateTime": "2024-06-15T10:00:00", "timeZone": "America/New_York"},
                "end": {"dateTime": "2024-06-15T11:00:00", "timeZone": "America/New_York"},
            }
        )
        event = mappers.to_calendar_event(raw, "c")
        assert event.start.tzinfo == ZoneInfo("America/New_York")
        # A 10:00 Eastern datetime is not 10:00 UTC
        assert event.start.utcoffset() is not None
        assert event.start.utcoffset().total_seconds() != 0

    def test_datetime_unknown_windows_tz_falls_back_to_utc(self):
        raw = _make_raw(
            {
                "start": {"dateTime": "2024-06-15T10:00:00", "timeZone": "Eastern Standard Time"},
                "end": {"dateTime": "2024-06-15T11:00:00", "timeZone": "Eastern Standard Time"},
            }
        )
        event = mappers.to_calendar_event(raw, "c")
        assert event.start.tzinfo == timezone.utc

    def test_all_day_event(self):
        raw = _make_raw({"isAllDay": True})
        event = mappers.to_calendar_event(raw, "c")
        assert event.all_day is True

    def test_status_mapping(self):
        for show_as, expected in [
            ("normal", EventStatus.CONFIRMED),
            ("tentative", EventStatus.TENTATIVE),
            ("cancelled", EventStatus.CANCELLED),
        ]:
            event = mappers.to_calendar_event(_make_raw({"showAs": show_as}), "c")
            assert event.status == expected

    def test_organizer_mapped(self):
        raw = _make_raw({"organizer": {"emailAddress": {"address": "boss@x.com", "name": "Boss"}}})
        event = mappers.to_calendar_event(raw, "c")
        assert event.organizer is not None
        assert event.organizer.email == "boss@x.com"
        assert event.organizer.display_name == "Boss"

    def test_attendees_mapped(self):
        raw = _make_raw(
            {
                "attendees": [
                    {
                        "emailAddress": {"address": "a@x.com", "name": "A"},
                        "status": {"response": "accepted"},
                    },
                    {
                        "emailAddress": {"address": "b@x.com", "name": "B"},
                        "status": {"response": "declined"},
                    },
                ]
            }
        )
        event = mappers.to_calendar_event(raw, "c")
        assert len(event.attendees) == 2
        assert event.attendees[0].status == AttendeeStatus.ACCEPTED
        assert event.attendees[1].status == AttendeeStatus.DECLINED

    def test_attendee_not_responded(self):
        raw = _make_raw(
            {
                "attendees": [
                    {
                        "emailAddress": {"address": "x@y.com"},
                        "status": {"response": "notResponded"},
                    },
                ]
            }
        )
        event = mappers.to_calendar_event(raw, "c")
        assert event.attendees[0].status == AttendeeStatus.NEEDS_ACTION

    def test_recurrence_preserved(self):
        rrule = {"pattern": {"type": "weekly"}, "range": {"type": "numbered"}}
        raw = _make_raw({"recurrence": rrule})
        event = mappers.to_calendar_event(raw, "c")
        assert event.recurrence is not None
        assert event.recurrence.provider_data == rrule

    def test_online_meeting_mapped_to_conference(self):
        raw = _make_raw(
            {"onlineMeeting": {"joinUrl": "https://teams.microsoft.com/l/meetup-join/abc"}}
        )
        event = mappers.to_calendar_event(raw, "c")
        assert event.conference_data is not None
        assert event.conference_data.join_url == "https://teams.microsoft.com/l/meetup-join/abc"

    def test_created_updated_timestamps(self):
        raw = _make_raw(
            {
                "createdDateTime": "2024-01-01T00:00:00Z",
                "lastModifiedDateTime": "2024-06-01T12:00:00Z",
            }
        )
        event = mappers.to_calendar_event(raw, "c")
        assert event.created_at is not None
        assert event.updated_at is not None

    def test_ical_uid_and_etag(self):
        raw = _make_raw({"iCalUId": "uid-123", "@odata.etag": 'W/"tag"'})
        event = mappers.to_calendar_event(raw, "c")
        assert event.ical_uid == "uid-123"
        assert event.etag == 'W/"tag"'

    def test_extra_keys_in_provider_data(self):
        raw = _make_raw({"sensitivity": "normal"})
        event = mappers.to_calendar_event(raw, "c")
        assert event.provider_data is not None
        assert "sensitivity" in event.provider_data

    def test_mapped_keys_not_in_provider_data(self):
        event = mappers.to_calendar_event(_make_raw(), "c")
        assert "id" not in (event.provider_data or {})
        assert "subject" not in (event.provider_data or {})


# --------------------------------------------------------------------------- #
# from_calendar_event                                                          #
# --------------------------------------------------------------------------- #


class TestFromCalendarEvent:
    def test_basic_fields(self):
        event = _make_event()
        body = mappers.from_calendar_event(event)
        assert body["subject"] == "MS Test Event"
        assert "start" in body
        assert "end" in body
        assert "isAllDay" in body

    def test_optional_fields_omitted_when_none(self):
        event = _make_event()
        body = mappers.from_calendar_event(event)
        assert "body" not in body
        assert "location" not in body

    def test_optional_fields_included(self):
        event = _make_event(description="desc", location="loc")
        body = mappers.from_calendar_event(event)
        assert body["body"]["content"] == "desc"
        assert body["location"]["displayName"] == "loc"

    def test_status_mapped(self):
        event = _make_event(status=EventStatus.TENTATIVE)
        body = mappers.from_calendar_event(event)
        assert body["showAs"] == "tentative"

    def test_attendees_mapped(self):
        event = _make_event(
            attendees=[
                Attendee(email="a@x.com", display_name="A"),
            ]
        )
        body = mappers.from_calendar_event(event)
        assert body["attendees"][0]["emailAddress"]["address"] == "a@x.com"
        assert body["attendees"][0]["type"] == "required"


# --------------------------------------------------------------------------- #
# to_calendar                                                                  #
# --------------------------------------------------------------------------- #


class TestToCalendar:
    def test_basic_fields(self):
        raw = {
            "id": "cal-1",
            "name": "My Calendar",
            "description": "desc",
            "timeZone": "UTC",
            "isDefaultCalendar": True,
            "canEdit": True,
            "hexColor": "#ff0000",
        }
        cal = mappers.to_calendar(raw)
        assert cal.calendar_id == "cal-1"
        assert cal.summary == "My Calendar"
        assert cal.is_primary is True
        assert cal.is_read_only is False
        assert cal.background_color == "#ff0000"

    def test_cannot_edit_is_read_only(self):
        raw = {"id": "c", "name": "s", "canEdit": False}
        cal = mappers.to_calendar(raw)
        assert cal.is_read_only is True

    def test_extra_keys_in_provider_data(self):
        raw = {"id": "c", "name": "s", "owner": {"name": "Me"}}
        cal = mappers.to_calendar(raw)
        assert cal.provider_data is not None
        assert "owner" in cal.provider_data

    def test_mapped_keys_not_in_provider_data(self):
        raw = {"id": "c", "name": "s", "timeZone": "UTC"}
        cal = mappers.to_calendar(raw)
        assert "id" not in (cal.provider_data or {})
        assert "name" not in (cal.provider_data or {})
