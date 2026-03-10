"""
Unit tests for omnidapter.providers.zoho.mappers.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from omnidapter.providers.zoho import mappers
from omnidapter.services.calendar.models import (
    Attendee,
    AttendeeStatus,
    CalendarEvent,
)

# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

def _make_raw(overrides: dict | None = None) -> dict:
    base = {
        "uid": "zoho-uid-1",
        "title": "Zoho Test Event",
        "dateandtime": {
            "start": "20240615T100000Z",
            "end": "20240615T110000Z",
        },
        "isallday": False,
    }
    if overrides:
        base.update(overrides)
    return base


def _make_event(**kwargs) -> CalendarEvent:
    defaults = dict(
        event_id="zoho-uid-1",
        calendar_id="cal-1",
        summary="Zoho Test Event",
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
        raw = _make_raw({"description": "desc", "location": "loc"})
        event = mappers.to_calendar_event(raw, "cal-1")
        assert event.event_id == "zoho-uid-1"
        assert event.calendar_id == "cal-1"
        assert event.summary == "Zoho Test Event"
        assert event.description == "desc"
        assert event.location == "loc"

    def test_uid_preferred_over_id(self):
        raw = _make_raw({"uid": "uid-primary", "id": "id-fallback"})
        event = mappers.to_calendar_event(raw, "c")
        assert event.event_id == "uid-primary"

    def test_id_fallback_when_no_uid(self):
        raw = {
            "id": "id-only",
            "title": "T",
            "dateandtime": {"start": "20240615T100000Z", "end": "20240615T110000Z"},
        }
        event = mappers.to_calendar_event(raw, "c")
        assert event.event_id == "id-only"

    def test_start_end_parsed(self):
        event = mappers.to_calendar_event(_make_raw(), "c")
        assert isinstance(event.start, datetime)
        assert event.start.hour == 10
        assert event.end.hour == 11

    def test_all_day_flag(self):
        raw = _make_raw({"isallday": True})
        event = mappers.to_calendar_event(raw, "c")
        assert event.all_day is True

    def test_attendees_mapped(self):
        raw = _make_raw({"attendees": [
            {"email": "a@x.com", "name": "Alice"},
            {"email": "b@x.com"},
        ]})
        event = mappers.to_calendar_event(raw, "c")
        assert len(event.attendees) == 2
        assert event.attendees[0].email == "a@x.com"
        assert event.attendees[0].display_name == "Alice"
        assert event.attendees[0].status == AttendeeStatus.NEEDS_ACTION

    def test_extra_keys_in_provider_data(self):
        raw = _make_raw({"etag": "tag-123"})
        event = mappers.to_calendar_event(raw, "c")
        assert event.provider_data is not None
        assert "etag" in event.provider_data

    def test_mapped_keys_not_in_provider_data(self):
        event = mappers.to_calendar_event(_make_raw(), "c")
        assert "uid" not in (event.provider_data or {})
        assert "title" not in (event.provider_data or {})
        assert "dateandtime" not in (event.provider_data or {})

    def test_iso_datetime_fallback(self):
        """_parse_zoho_datetime falls back to fromisoformat for non-compact strings."""
        raw = _make_raw()
        raw["dateandtime"]["start"] = "2024-06-15T10:00:00+00:00"
        event = mappers.to_calendar_event(raw, "c")
        assert isinstance(event.start, datetime)

    def test_missing_datetime_uses_now(self):
        raw = {"uid": "x", "title": "T", "dateandtime": {}}
        event = mappers.to_calendar_event(raw, "c")
        assert isinstance(event.start, datetime)


# --------------------------------------------------------------------------- #
# from_calendar_event                                                          #
# --------------------------------------------------------------------------- #

class TestFromCalendarEvent:
    def test_basic_fields(self):
        event = _make_event()
        body = mappers.from_calendar_event(event)
        assert body["title"] == "Zoho Test Event"
        assert "dateandtime" in body
        assert "isallday" in body

    def test_datetime_format(self):
        event = _make_event()
        body = mappers.from_calendar_event(event)
        assert body["dateandtime"]["start"] == "20240615T100000Z"

    def test_all_day_date_format(self):
        event = _make_event(start=date(2024, 6, 15), end=date(2024, 6, 16), all_day=True)
        body = mappers.from_calendar_event(event)
        assert body["dateandtime"]["start"] == "20240615"

    def test_optional_fields_omitted_when_none(self):
        event = _make_event()
        body = mappers.from_calendar_event(event)
        assert "description" not in body
        assert "location" not in body

    def test_optional_fields_included(self):
        event = _make_event(description="d", location="l")
        body = mappers.from_calendar_event(event)
        assert body["description"] == "d"
        assert body["location"] == "l"

    def test_attendees_mapped(self):
        event = _make_event(attendees=[
            Attendee(email="a@x.com", display_name="Alice"),
            Attendee(email="b@x.com"),
        ])
        body = mappers.from_calendar_event(event)
        assert body["attendees"][0]["email"] == "a@x.com"
        assert body["attendees"][0]["name"] == "Alice"
        assert body["attendees"][1]["name"] == "b@x.com"  # falls back to email


# --------------------------------------------------------------------------- #
# to_calendar                                                                  #
# --------------------------------------------------------------------------- #

class TestToCalendar:
    def test_basic_fields(self):
        raw = {
            "uid": "cal-uid",
            "name": "My Zoho Calendar",
            "description": "desc",
            "timezone": "UTC",
            "isprimary": True,
        }
        cal = mappers.to_calendar(raw)
        assert cal.calendar_id == "cal-uid"
        assert cal.summary == "My Zoho Calendar"
        assert cal.is_primary is True
        assert cal.timezone == "UTC"

    def test_id_fallback(self):
        raw = {"id": "id-only", "name": "s"}
        cal = mappers.to_calendar(raw)
        assert cal.calendar_id == "id-only"

    def test_extra_keys_in_provider_data(self):
        raw = {"uid": "c", "name": "s", "extra": "value"}
        cal = mappers.to_calendar(raw)
        assert cal.provider_data is not None
        assert cal.provider_data["extra"] == "value"

    def test_mapped_keys_not_in_provider_data(self):
        raw = {"uid": "c", "name": "s", "description": "d", "timezone": "UTC", "isprimary": True}
        cal = mappers.to_calendar(raw)
        for key in ("uid", "name", "description", "timezone", "isprimary"):
            assert key not in (cal.provider_data or {})
