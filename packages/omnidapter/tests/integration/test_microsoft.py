"""
Integration tests for Microsoft Calendar (Graph API).

Required env vars:
    OMNIDAPTER_INTEGRATION=1
    OMNIDAPTER_TEST_MICROSOFT_CLIENT_ID
    OMNIDAPTER_TEST_MICROSOFT_CLIENT_SECRET
    OMNIDAPTER_TEST_MICROSOFT_REFRESH_TOKEN

Optional:
    OMNIDAPTER_TEST_MICROSOFT_CALENDAR_ID  (defaults to first calendar on the account)

Use a dedicated test Microsoft account. Tests create and delete events but never
touch data they did not create.
"""
from __future__ import annotations

import os
from contextlib import suppress
from datetime import date, datetime, timedelta, timezone

import pytest

from omnidapter.services.calendar.models import (
    Attendee,
    CalendarEvent,
    EventStatus,
)
from omnidapter.services.calendar.requests import (
    CreateEventRequest,
    GetAvailabilityRequest,
    UpdateEventRequest,
)

from .conftest import EVENT_PREFIX, PAGINATION_PAGE_SIZE, _stale_oauth2_stored

pytestmark = pytest.mark.integration


# --------------------------------------------------------------------------- #
# Token refresh                                                                #
# --------------------------------------------------------------------------- #

async def test_token_refresh():
    """
    Expired access token + valid refresh token → fresh credentials that work.
    """
    from omnidapter.providers.microsoft.provider import MicrosoftProvider

    stale = _stale_oauth2_stored(
        "microsoft", os.environ["OMNIDAPTER_TEST_MICROSOFT_REFRESH_TOKEN"]
    )
    assert stale.credentials.is_expired()

    provider = MicrosoftProvider(
        client_id=os.environ["OMNIDAPTER_TEST_MICROSOFT_CLIENT_ID"],
        client_secret=os.environ["OMNIDAPTER_TEST_MICROSOFT_CLIENT_SECRET"],
    )
    refreshed = await provider.refresh_token(stale)

    new_creds = refreshed.credentials
    assert new_creds.access_token
    assert new_creds.access_token != "stale-will-be-refreshed"
    assert not new_creds.is_expired()

    svc = provider.get_calendar_service("test-token-refresh", refreshed)
    calendars = await svc.list_calendars()
    assert len(calendars) >= 1


# --------------------------------------------------------------------------- #
# Calendar discovery                                                           #
# --------------------------------------------------------------------------- #

async def test_list_calendars(microsoft_service):
    """list_calendars() returns at least one Calendar with required fields."""
    calendars = await microsoft_service.list_calendars()
    assert len(calendars) >= 1
    for cal in calendars:
        assert cal.calendar_id
        assert isinstance(cal.summary, str)


# --------------------------------------------------------------------------- #
# CRUD round-trip                                                              #
# --------------------------------------------------------------------------- #

async def test_crud_round_trip(microsoft_service, microsoft_calendar_id, retry_read):
    """
    Create → read → update → delete with field-level assertions at each step.
    """
    now = datetime.now(timezone.utc).replace(microsecond=0)
    created_ids: list[str] = []

    try:
        # ── Create ──────────────────────────────────────────────────────────
        req = CreateEventRequest(
            calendar_id=microsoft_calendar_id,
            summary=f"{EVENT_PREFIX} crud round-trip",
            start=now + timedelta(hours=1),
            end=now + timedelta(hours=2),
            description="Integration test event — please ignore",
            location="42 Integration Lane",
            timezone="UTC",
        )
        created = await microsoft_service.create_event(req)
        created_ids.append(created.event_id)

        assert created.event_id
        assert created.summary == req.summary
        assert created.calendar_id == microsoft_calendar_id

        # ── Read back ────────────────────────────────────────────────────────
        fetched = await retry_read(
            lambda: microsoft_service.get_event(microsoft_calendar_id, created.event_id)
        )
        assert fetched.summary == req.summary
        assert fetched.description == req.description
        assert fetched.location == req.location
        assert isinstance(fetched.start, datetime)
        assert isinstance(fetched.end, datetime)

        # ── Update ───────────────────────────────────────────────────────────
        update_req = UpdateEventRequest(
            calendar_id=microsoft_calendar_id,
            event_id=created.event_id,
            summary=f"{EVENT_PREFIX} crud round-trip (updated)",
            description="Updated by integration test",
        )
        updated = await microsoft_service.update_event(update_req)
        assert updated.summary == update_req.summary

        fetched_after_update = await retry_read(
            lambda: microsoft_service.get_event(microsoft_calendar_id, created.event_id)
        )
        assert fetched_after_update.summary == update_req.summary
        assert fetched_after_update.description == update_req.description

        # ── Delete ───────────────────────────────────────────────────────────
        await microsoft_service.delete_event(microsoft_calendar_id, created.event_id)
        created_ids.remove(created.event_id)

        from omnidapter.core.errors import ProviderAPIError

        with pytest.raises(ProviderAPIError):
            await retry_read(
                lambda: microsoft_service.get_event(
                    microsoft_calendar_id, created.event_id
                ),
                max_attempts=1,
            )

    finally:
        for eid in created_ids:
            with suppress(Exception):
                await microsoft_service.delete_event(microsoft_calendar_id, eid)


# --------------------------------------------------------------------------- #
# Mapper fidelity                                                              #
# --------------------------------------------------------------------------- #

async def test_mapper_fidelity(microsoft_service, microsoft_calendar_id, retry_read):
    """
    Verify the Microsoft Graph → CalendarEvent mapper handles real API response
    shapes, including Graph-specific fields (showAs → status, subject → summary,
    body → description, webLink → html_link, iCalUId → ical_uid, @odata.etag → etag).
    """
    now = datetime.now(timezone.utc).replace(microsecond=0)
    req = CreateEventRequest(
        calendar_id=microsoft_calendar_id,
        summary=f"{EVENT_PREFIX} mapper fidelity",
        start=now + timedelta(hours=1),
        end=now + timedelta(hours=2),
        description="Testing field-mapping fidelity",
        location="Mapper Test Location",
        timezone="UTC",
        attendees=[
            Attendee(email="integration-attendee@example.com", display_name="Test Attendee")
        ],
    )
    event_id: str | None = None

    try:
        created = await microsoft_service.create_event(req)
        event_id = created.event_id

        fetched = await retry_read(
            lambda: microsoft_service.get_event(microsoft_calendar_id, event_id)
        )

        assert isinstance(fetched, CalendarEvent)
        assert fetched.event_id
        assert fetched.calendar_id == microsoft_calendar_id
        assert fetched.summary == req.summary
        assert fetched.description == req.description
        assert fetched.location == req.location
        assert isinstance(fetched.start, datetime)
        assert isinstance(fetched.end, datetime)
        assert fetched.status in EventStatus
        assert fetched.created_at is not None
        assert fetched.updated_at is not None
        assert fetched.ical_uid is not None
        assert fetched.html_link is not None
        assert fetched.etag is not None
        assert len(fetched.attendees) >= 1

    finally:
        if event_id:
            with suppress(Exception):
                await microsoft_service.delete_event(microsoft_calendar_id, event_id)


# --------------------------------------------------------------------------- #
# All-day event                                                                #
# --------------------------------------------------------------------------- #

async def test_all_day_event(microsoft_service, microsoft_calendar_id, retry_read):
    """All-day events use the isAllDay flag; verify mapper honours it."""
    today = datetime.now(timezone.utc).date()
    req = CreateEventRequest(
        calendar_id=microsoft_calendar_id,
        summary=f"{EVENT_PREFIX} all-day event",
        start=today + timedelta(days=1),
        end=today + timedelta(days=2),
        all_day=True,
        timezone="UTC",
    )
    event_id: str | None = None

    try:
        created = await microsoft_service.create_event(req)
        event_id = created.event_id

        fetched = await retry_read(
            lambda: microsoft_service.get_event(microsoft_calendar_id, event_id)
        )
        assert fetched.all_day is True

    finally:
        if event_id:
            with suppress(Exception):
                await microsoft_service.delete_event(microsoft_calendar_id, event_id)


# --------------------------------------------------------------------------- #
# Pagination                                                                   #
# --------------------------------------------------------------------------- #

async def test_pagination(microsoft_service, microsoft_calendar_id):
    """
    Create PAGINATION_PAGE_SIZE + 2 events, verify all are returned across
    pages when page_size < event count.
    """
    n = PAGINATION_PAGE_SIZE + 2
    now = datetime.now(timezone.utc).replace(microsecond=0)
    created_ids: list[str] = []

    try:
        for i in range(n):
            req = CreateEventRequest(
                calendar_id=microsoft_calendar_id,
                summary=f"{EVENT_PREFIX} pagination-{i:02d}",
                start=now + timedelta(hours=i + 1),
                end=now + timedelta(hours=i + 1, minutes=30),
                timezone="UTC",
            )
            event = await microsoft_service.create_event(req)
            created_ids.append(event.event_id)

        collected: list[CalendarEvent] = []
        async for event in microsoft_service.list_events(
            microsoft_calendar_id,
            time_min=now,
            time_max=now + timedelta(hours=n + 2),
            page_size=PAGINATION_PAGE_SIZE,
        ):
            if f"{EVENT_PREFIX} pagination-" in (event.summary or ""):
                collected.append(event)

        assert len(collected) >= n, (
            f"Expected at least {n} test events from pagination, got {len(collected)}"
        )

    finally:
        for eid in created_ids:
            with suppress(Exception):
                await microsoft_service.delete_event(microsoft_calendar_id, eid)


# --------------------------------------------------------------------------- #
# Availability (free/busy)                                                     #
# --------------------------------------------------------------------------- #

async def test_get_availability(microsoft_service, microsoft_calendar_id):
    """get_availability() returns a well-formed AvailabilityResponse."""
    now = datetime.now(timezone.utc)
    req = GetAvailabilityRequest(
        calendar_ids=[microsoft_calendar_id],
        time_min=now,
        time_max=now + timedelta(days=7),
    )
    result = await microsoft_service.get_availability(req)

    assert result.queried_calendars == [microsoft_calendar_id]
    assert isinstance(result.busy_intervals, list)
    for interval in result.busy_intervals:
        assert isinstance(interval.start, datetime)
        assert isinstance(interval.end, datetime)
        assert interval.start < interval.end
