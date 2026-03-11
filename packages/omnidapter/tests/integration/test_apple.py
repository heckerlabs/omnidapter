"""
Integration tests for Apple Calendar (iCloud CalDAV).

Required env vars:
    OMNIDAPTER_INTEGRATION=1
    OMNIDAPTER_TEST_APPLE_USERNAME   (Apple ID email address)
    OMNIDAPTER_TEST_APPLE_PASSWORD   (App-specific password — NOT your Apple ID password)

Optional:
    OMNIDAPTER_TEST_APPLE_CALENDAR_ID  (defaults to first discovered calendar)

Apple Calendar uses CalDAV under the hood with a fixed server URL
(https://caldav.icloud.com). Authentication requires an app-specific
password generated at appleid.apple.com, not the account password.

Apple Calendar uses Basic auth, not OAuth, so there is no token-refresh test.
"""
from __future__ import annotations

from contextlib import suppress
from datetime import date, datetime, timedelta, timezone

import pytest
from omnidapter.services.calendar.models import (
    Attendee,
    CalendarEvent,
    EventStatus,
)
from omnidapter.services.calendar.requests import CreateEventRequest, UpdateEventRequest

from .conftest import EVENT_PREFIX, PAGINATION_PAGE_SIZE

pytestmark = pytest.mark.integration


# --------------------------------------------------------------------------- #
# Server discovery                                                             #
# --------------------------------------------------------------------------- #

async def test_apple_discovery(apple_service):
    """
    PROPFIND to caldav.icloud.com discovers at least one calendar collection.

    Verifies that the hardcoded iCloud URL, Basic auth header, and XML
    parsing all work against the real iCloud CalDAV endpoint.
    """
    calendars = await apple_service.list_calendars()
    assert len(calendars) >= 1
    for cal in calendars:
        assert cal.calendar_id
        assert isinstance(cal.summary, str)


# --------------------------------------------------------------------------- #
# CRUD round-trip                                                              #
# --------------------------------------------------------------------------- #

async def test_crud_round_trip(apple_service, apple_calendar_id, retry_read):
    """Create → read → update → delete with field-level assertions at each step."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    created_uid: str | None = None

    try:
        req = CreateEventRequest(
            calendar_id=apple_calendar_id,
            summary=f"{EVENT_PREFIX} crud round-trip",
            start=now + timedelta(hours=1),
            end=now + timedelta(hours=2),
            description="Integration test event — please ignore",
            location="42 Integration Lane",
        )
        created = await apple_service.create_event(req)
        created_uid = created.event_id

        assert created.event_id
        assert created.summary == req.summary

        fetched = await retry_read(
            lambda: apple_service.get_event(apple_calendar_id, created.event_id)
        )
        assert fetched.summary == req.summary
        assert fetched.description == req.description
        assert fetched.location == req.location
        assert isinstance(fetched.start, datetime)
        assert isinstance(fetched.end, datetime)
        assert fetched.ical_uid == created.event_id

        update_req = UpdateEventRequest(
            calendar_id=apple_calendar_id,
            event_id=created.event_id,
            summary=f"{EVENT_PREFIX} crud round-trip (updated)",
            description="Updated by integration test",
        )
        await apple_service.update_event(update_req)

        fetched_after_update = await retry_read(
            lambda: apple_service.get_event(apple_calendar_id, created.event_id)
        )
        assert fetched_after_update.summary == update_req.summary
        assert fetched_after_update.description == update_req.description

        await apple_service.delete_event(apple_calendar_id, created.event_id)
        created_uid = None

        from omnidapter.core.errors import ProviderAPIError

        with pytest.raises(ProviderAPIError):
            await retry_read(
                lambda: apple_service.get_event(apple_calendar_id, created.event_id),
                max_attempts=1,
            )

    finally:
        if created_uid:
            with suppress(Exception):
                await apple_service.delete_event(apple_calendar_id, created_uid)


# --------------------------------------------------------------------------- #
# Mapper fidelity                                                              #
# --------------------------------------------------------------------------- #

async def test_mapper_fidelity(apple_service, apple_calendar_id, retry_read):
    """Verify that all supported iCalendar fields round-trip through iCloud."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    req = CreateEventRequest(
        calendar_id=apple_calendar_id,
        summary=f"{EVENT_PREFIX} mapper fidelity",
        start=now + timedelta(hours=1),
        end=now + timedelta(hours=2),
        description="Testing iCalendar field-mapping fidelity",
        location="Mapper Test Location",
        attendees=[
            Attendee(email="integration-attendee@example.com", display_name="Test Attendee")
        ],
    )
    event_id: str | None = None

    try:
        created = await apple_service.create_event(req)
        event_id = created.event_id

        fetched = await retry_read(
            lambda: apple_service.get_event(apple_calendar_id, event_id)
        )

        assert isinstance(fetched, CalendarEvent)
        assert fetched.event_id
        assert fetched.summary == req.summary
        assert fetched.description == req.description
        assert fetched.location == req.location
        assert isinstance(fetched.start, datetime)
        assert isinstance(fetched.end, datetime)
        assert fetched.status in EventStatus
        assert fetched.ical_uid is not None
        assert len(fetched.attendees) >= 1
        assert any(a.email == "integration-attendee@example.com" for a in fetched.attendees)
        assert fetched.provider_data is not None
        assert "raw_props" in fetched.provider_data

    finally:
        if event_id:
            with suppress(Exception):
                await apple_service.delete_event(apple_calendar_id, event_id)


# --------------------------------------------------------------------------- #
# All-day event                                                                #
# --------------------------------------------------------------------------- #

async def test_all_day_event(apple_service, apple_calendar_id, retry_read):
    """iCalendar DATE (not DATE-TIME) properties map to Python date objects."""
    today = datetime.now(timezone.utc).date()
    req = CreateEventRequest(
        calendar_id=apple_calendar_id,
        summary=f"{EVENT_PREFIX} all-day event",
        start=today + timedelta(days=1),
        end=today + timedelta(days=2),
        all_day=True,
    )
    event_id: str | None = None

    try:
        created = await apple_service.create_event(req)
        event_id = created.event_id

        fetched = await retry_read(
            lambda: apple_service.get_event(apple_calendar_id, event_id)
        )
        assert fetched.all_day is True
        assert isinstance(fetched.start, date)
        assert not isinstance(fetched.start, datetime)

    finally:
        if event_id:
            with suppress(Exception):
                await apple_service.delete_event(apple_calendar_id, event_id)


# --------------------------------------------------------------------------- #
# Recurrence                                                                   #
# --------------------------------------------------------------------------- #

async def test_recurring_event(apple_service, apple_calendar_id, retry_read):
    """RRULE lines in the VCALENDAR are preserved in the Recurrence model."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    from omnidapter.services.calendar.models import Recurrence

    req = CreateEventRequest(
        calendar_id=apple_calendar_id,
        summary=f"{EVENT_PREFIX} recurring weekly",
        start=now + timedelta(hours=1),
        end=now + timedelta(hours=2),
        recurrence=Recurrence(rules=["RRULE:FREQ=WEEKLY;COUNT=4"]),
    )
    event_id: str | None = None

    try:
        created = await apple_service.create_event(req)
        event_id = created.event_id

        fetched = await retry_read(
            lambda: apple_service.get_event(apple_calendar_id, event_id)
        )
        assert fetched.recurrence is not None
        assert any("RRULE" in rule for rule in fetched.recurrence.rules)

    finally:
        if event_id:
            with suppress(Exception):
                await apple_service.delete_event(apple_calendar_id, event_id)


# --------------------------------------------------------------------------- #
# Pagination (REPORT query)                                                    #
# --------------------------------------------------------------------------- #

async def test_pagination(apple_service, apple_calendar_id):
    """
    Create PAGINATION_PAGE_SIZE + 2 events and verify all are returned by
    a time-bounded REPORT query.

    iCloud CalDAV returns all matching VEVENTs in a single multi-status
    response; this test verifies correct XML parsing when multiple events
    are present.
    """
    n = PAGINATION_PAGE_SIZE + 2
    now = datetime.now(timezone.utc).replace(microsecond=0)
    created_uids: list[str] = []

    try:
        for i in range(n):
            req = CreateEventRequest(
                calendar_id=apple_calendar_id,
                summary=f"{EVENT_PREFIX} pagination-{i:02d}",
                start=now + timedelta(hours=i + 1),
                end=now + timedelta(hours=i + 1, minutes=30),
            )
            event = await apple_service.create_event(req)
            created_uids.append(event.event_id)

        collected: list[CalendarEvent] = []
        async for event in apple_service.list_events(
            apple_calendar_id,
            time_min=now,
            time_max=now + timedelta(hours=n + 2),
        ):
            if f"{EVENT_PREFIX} pagination-" in (event.summary or ""):
                collected.append(event)

        assert len(collected) >= n, (
            f"Expected at least {n} test events, got {len(collected)}"
        )

    finally:
        for uid in created_uids:
            with suppress(Exception):
                await apple_service.delete_event(apple_calendar_id, uid)
