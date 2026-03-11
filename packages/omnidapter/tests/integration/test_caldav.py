"""
Integration tests for CalDAV.

Required env vars:
    OMNIDAPTER_INTEGRATION=1
    OMNIDAPTER_TEST_CALDAV_URL        (e.g. http://localhost:5232 for Radicale,
                                       or a real server like iCloud / Fastmail)
    OMNIDAPTER_TEST_CALDAV_USERNAME
    OMNIDAPTER_TEST_CALDAV_PASSWORD

Optional:
    OMNIDAPTER_TEST_CALDAV_CALENDAR_ID  (defaults to first discovered calendar)

CI recommendation: run a local Radicale instance in Docker so the CalDAV URL
points to localhost. For pre-release manual testing, point it at a real server
(iCloud, Fastmail, Nextcloud) to surface server-specific quirks.

CalDAV uses Basic auth, not OAuth, so there is no token-refresh test.
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


async def test_caldav_discovery(caldav_service):
    """
    PROPFIND to the server URL discovers at least one calendar collection.

    This tests the full CalDAV discovery flow: HTTP construction, Basic auth
    header, XML parsing, and calendar URL extraction.
    """
    calendars = await caldav_service.list_calendars()
    assert len(calendars) >= 1
    for cal in calendars:
        assert cal.calendar_id  # href path
        assert isinstance(cal.summary, str)


# --------------------------------------------------------------------------- #
# CRUD round-trip                                                              #
# --------------------------------------------------------------------------- #


async def test_crud_round_trip(caldav_service, caldav_calendar_id, retry_read):
    """
    Create → read → update → delete with field-level assertions at each step.

    CalDAV stores events as iCalendar text (PUT/GET .ics resources). The mapper
    parses VEVENT blocks; this test verifies the full parse/serialise cycle.
    """
    now = datetime.now(timezone.utc).replace(microsecond=0)
    created_uid: str | None = None

    try:
        # ── Create ──────────────────────────────────────────────────────────
        req = CreateEventRequest(
            calendar_id=caldav_calendar_id,
            summary=f"{EVENT_PREFIX} crud round-trip",
            start=now + timedelta(hours=1),
            end=now + timedelta(hours=2),
            description="Integration test event — please ignore",
            location="42 Integration Lane",
        )
        created = await caldav_service.create_event(req)
        created_uid = created.event_id

        assert created.event_id
        assert created.summary == req.summary

        # ── Read back ────────────────────────────────────────────────────────
        fetched = await retry_read(
            lambda: caldav_service.get_event(caldav_calendar_id, created.event_id)
        )
        assert fetched.summary == req.summary
        assert fetched.description == req.description
        assert fetched.location == req.location
        assert isinstance(fetched.start, datetime)
        assert isinstance(fetched.end, datetime)
        assert fetched.ical_uid == created.event_id

        # ── Update ───────────────────────────────────────────────────────────
        update_req = UpdateEventRequest(
            calendar_id=caldav_calendar_id,
            event_id=created.event_id,
            summary=f"{EVENT_PREFIX} crud round-trip (updated)",
            description="Updated by integration test",
        )
        await caldav_service.update_event(update_req)

        fetched_after_update = await retry_read(
            lambda: caldav_service.get_event(caldav_calendar_id, created.event_id)
        )
        assert fetched_after_update.summary == update_req.summary
        assert fetched_after_update.description == update_req.description

        # ── Delete ───────────────────────────────────────────────────────────
        await caldav_service.delete_event(caldav_calendar_id, created.event_id)
        created_uid = None

        from omnidapter.core.errors import ProviderAPIError

        with pytest.raises(ProviderAPIError):
            await retry_read(
                lambda: caldav_service.get_event(caldav_calendar_id, created.event_id),
                max_attempts=1,
            )

    finally:
        if created_uid:
            with suppress(Exception):
                await caldav_service.delete_event(caldav_calendar_id, created_uid)


# --------------------------------------------------------------------------- #
# Mapper fidelity (iCalendar parser)                                          #
# --------------------------------------------------------------------------- #


async def test_mapper_fidelity(caldav_service, caldav_calendar_id, retry_read):
    """
    Verify that the iCalendar VEVENT parser correctly maps all supported fields
    from a real server response.
    """
    now = datetime.now(timezone.utc).replace(microsecond=0)
    req = CreateEventRequest(
        calendar_id=caldav_calendar_id,
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
        created = await caldav_service.create_event(req)
        event_id = created.event_id

        fetched = await retry_read(lambda: caldav_service.get_event(caldav_calendar_id, event_id))

        assert isinstance(fetched, CalendarEvent)
        assert fetched.event_id
        assert fetched.summary == req.summary
        assert fetched.description == req.description
        assert fetched.location == req.location
        assert isinstance(fetched.start, datetime)
        assert isinstance(fetched.end, datetime)
        assert fetched.status in EventStatus
        assert fetched.ical_uid is not None
        # Attendees are included in the VCALENDAR and should round-trip.
        assert len(fetched.attendees) >= 1
        assert any(a.email == "integration-attendee@example.com" for a in fetched.attendees)
        # raw_props in provider_data lets callers access unmapped iCal properties.
        assert fetched.provider_data is not None
        assert "raw_props" in fetched.provider_data

    finally:
        if event_id:
            with suppress(Exception):
                await caldav_service.delete_event(caldav_calendar_id, event_id)


# --------------------------------------------------------------------------- #
# All-day event                                                                #
# --------------------------------------------------------------------------- #


async def test_all_day_event(caldav_service, caldav_calendar_id, retry_read):
    """
    iCalendar DATE (not DATE-TIME) properties map to Python date objects.
    """
    today = datetime.now(timezone.utc).date()
    req = CreateEventRequest(
        calendar_id=caldav_calendar_id,
        summary=f"{EVENT_PREFIX} all-day event",
        start=today + timedelta(days=1),
        end=today + timedelta(days=2),
        all_day=True,
    )
    event_id: str | None = None

    try:
        created = await caldav_service.create_event(req)
        event_id = created.event_id

        fetched = await retry_read(lambda: caldav_service.get_event(caldav_calendar_id, event_id))
        assert fetched.all_day is True
        assert isinstance(fetched.start, date)
        assert not isinstance(fetched.start, datetime)

    finally:
        if event_id:
            with suppress(Exception):
                await caldav_service.delete_event(caldav_calendar_id, event_id)


# --------------------------------------------------------------------------- #
# Recurrence                                                                   #
# --------------------------------------------------------------------------- #


async def test_recurring_event(caldav_service, caldav_calendar_id, retry_read):
    """RRULE lines in the VCALENDAR are preserved in the Recurrence model."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    from omnidapter.services.calendar.models import Recurrence

    req = CreateEventRequest(
        calendar_id=caldav_calendar_id,
        summary=f"{EVENT_PREFIX} recurring weekly",
        start=now + timedelta(hours=1),
        end=now + timedelta(hours=2),
        recurrence=Recurrence(rules=["RRULE:FREQ=WEEKLY;COUNT=4"]),
    )
    event_id: str | None = None

    try:
        created = await caldav_service.create_event(req)
        event_id = created.event_id

        fetched = await retry_read(lambda: caldav_service.get_event(caldav_calendar_id, event_id))
        assert fetched.recurrence is not None
        assert any("RRULE" in rule for rule in fetched.recurrence.rules)

    finally:
        if event_id:
            with suppress(Exception):
                await caldav_service.delete_event(caldav_calendar_id, event_id)


# --------------------------------------------------------------------------- #
# Pagination (REPORT query)                                                    #
# --------------------------------------------------------------------------- #


async def test_pagination(caldav_service, caldav_calendar_id):
    """
    Create PAGINATION_PAGE_SIZE + 2 events, run a time-bounded REPORT query,
    and verify all events come back.

    CalDAV does not use cursor-based pagination; the REPORT query returns all
    matching VEVENTs in a single multi-status response. This test verifies that
    the REPORT request is constructed correctly and all VEVENT elements are
    parsed by the mapper.
    """
    n = PAGINATION_PAGE_SIZE + 2
    now = datetime.now(timezone.utc).replace(microsecond=0)
    created_uids: list[str] = []

    try:
        for i in range(n):
            req = CreateEventRequest(
                calendar_id=caldav_calendar_id,
                summary=f"{EVENT_PREFIX} pagination-{i:02d}",
                start=now + timedelta(hours=i + 1),
                end=now + timedelta(hours=i + 1, minutes=30),
            )
            event = await caldav_service.create_event(req)
            created_uids.append(event.event_id)

        collected: list[CalendarEvent] = []
        async for event in caldav_service.list_events(
            caldav_calendar_id,
            time_min=now,
            time_max=now + timedelta(hours=n + 2),
        ):
            if f"{EVENT_PREFIX} pagination-" in (event.summary or ""):
                collected.append(event)

        assert len(collected) >= n, f"Expected at least {n} test events, got {len(collected)}"

    finally:
        for uid in created_uids:
            with suppress(Exception):
                await caldav_service.delete_event(caldav_calendar_id, uid)
