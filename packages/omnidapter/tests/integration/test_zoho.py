"""
Integration tests for Zoho Calendar.

Required env vars:
    OMNIDAPTER_INTEGRATION=1
    OMNIDAPTER_TEST_ZOHO_CLIENT_ID
    OMNIDAPTER_TEST_ZOHO_CLIENT_SECRET
    OMNIDAPTER_TEST_ZOHO_REFRESH_TOKEN

Optional:
    OMNIDAPTER_TEST_ZOHO_CALENDAR_ID   (defaults to first calendar on the account)

Use a dedicated test Zoho account. Tests create and delete events but never
touch data they did not create.

Notes on Zoho limitations:
  - No availability (free/busy) endpoint in the API.
  - No webhook / push-notification support.
  - The Zoho API wraps events in {"events": [...]} envelopes; the mapper
    must handle both create/update responses and get/list responses.
"""

from __future__ import annotations

import os
from contextlib import suppress
from datetime import datetime, timedelta, timezone

import pytest
from omnidapter.services.calendar.models import CalendarEvent, EventStatus
from omnidapter.services.calendar.requests import CreateEventRequest, UpdateEventRequest

from .conftest import EVENT_PREFIX, PAGINATION_PAGE_SIZE, _stale_oauth2_stored

pytestmark = pytest.mark.integration


# --------------------------------------------------------------------------- #
# Token refresh                                                                #
# --------------------------------------------------------------------------- #


async def test_token_refresh():
    """
    Expired access token + valid refresh token → fresh credentials that work.
    """
    from omnidapter.providers.zoho.provider import ZohoProvider

    stale = _stale_oauth2_stored("zoho", os.environ["OMNIDAPTER_TEST_ZOHO_REFRESH_TOKEN"])
    assert stale.credentials.is_expired()

    provider = ZohoProvider(
        client_id=os.environ["OMNIDAPTER_TEST_ZOHO_CLIENT_ID"],
        client_secret=os.environ["OMNIDAPTER_TEST_ZOHO_CLIENT_SECRET"],
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


async def test_list_calendars(zoho_service):
    """list_calendars() returns at least one Calendar with required fields."""
    calendars = await zoho_service.list_calendars()
    assert len(calendars) >= 1
    for cal in calendars:
        assert cal.calendar_id
        assert isinstance(cal.summary, str)


# --------------------------------------------------------------------------- #
# CRUD round-trip                                                              #
# --------------------------------------------------------------------------- #


async def test_crud_round_trip(zoho_service, zoho_calendar_id, retry_read):
    """
    Create → read → update → delete with field-level assertions at each step.

    Zoho wraps its event responses in an "events" list; the mapper and service
    must unwrap them correctly for every operation.
    """
    now = datetime.now(timezone.utc).replace(microsecond=0)
    created_ids: list[str] = []

    try:
        # ── Create ──────────────────────────────────────────────────────────
        req = CreateEventRequest(
            calendar_id=zoho_calendar_id,
            summary=f"{EVENT_PREFIX} crud round-trip",
            start=now + timedelta(hours=1),
            end=now + timedelta(hours=2),
            description="Integration test event — please ignore",
            location="42 Integration Lane",
        )
        created = await zoho_service.create_event(req)
        created_ids.append(created.event_id)

        assert created.event_id
        assert created.summary == req.summary

        # ── Read back ────────────────────────────────────────────────────────
        fetched = await retry_read(
            lambda: zoho_service.get_event(zoho_calendar_id, created.event_id)
        )
        assert fetched.summary == req.summary

        # ── Update ───────────────────────────────────────────────────────────
        update_req = UpdateEventRequest(
            calendar_id=zoho_calendar_id,
            event_id=created.event_id,
            summary=f"{EVENT_PREFIX} crud round-trip (updated)",
            description="Updated by integration test",
        )
        updated = await zoho_service.update_event(update_req)
        assert updated.summary == update_req.summary

        fetched_after_update = await retry_read(
            lambda: zoho_service.get_event(zoho_calendar_id, created.event_id)
        )
        assert fetched_after_update.summary == update_req.summary

        # ── Delete ───────────────────────────────────────────────────────────
        await zoho_service.delete_event(zoho_calendar_id, created.event_id)
        created_ids.remove(created.event_id)

        from omnidapter.core.errors import ProviderAPIError

        with pytest.raises(ProviderAPIError):
            await retry_read(
                lambda: zoho_service.get_event(zoho_calendar_id, created.event_id),
                max_attempts=1,
            )

    finally:
        for eid in created_ids:
            with suppress(Exception):
                await zoho_service.delete_event(zoho_calendar_id, eid)


# --------------------------------------------------------------------------- #
# Mapper fidelity                                                              #
# --------------------------------------------------------------------------- #


async def test_mapper_fidelity(zoho_service, zoho_calendar_id, retry_read):
    """
    Verify that the Zoho → CalendarEvent mapper handles real API response
    shapes, including Zoho's compact datetime format and event-envelope wrapping.
    """
    now = datetime.now(timezone.utc).replace(microsecond=0)
    req = CreateEventRequest(
        calendar_id=zoho_calendar_id,
        summary=f"{EVENT_PREFIX} mapper fidelity",
        start=now + timedelta(hours=1),
        end=now + timedelta(hours=2),
        description="Testing field-mapping fidelity",
        location="Mapper Test Location",
    )
    event_id: str | None = None

    try:
        created = await zoho_service.create_event(req)
        event_id = created.event_id

        fetched = await retry_read(lambda: zoho_service.get_event(zoho_calendar_id, event_id))

        assert isinstance(fetched, CalendarEvent)
        assert fetched.event_id
        assert fetched.summary == req.summary
        assert isinstance(fetched.start, datetime)
        assert isinstance(fetched.end, datetime)
        assert fetched.status in EventStatus

    finally:
        if event_id:
            with suppress(Exception):
                await zoho_service.delete_event(zoho_calendar_id, event_id)


# --------------------------------------------------------------------------- #
# Pagination                                                                   #
# --------------------------------------------------------------------------- #


async def test_pagination(zoho_service, zoho_calendar_id):
    """
    Create PAGINATION_PAGE_SIZE + 2 events, verify all are returned when
    iterating with a page size smaller than the event count.

    Zoho uses a time-bounded query, so all events are returned in a single fetch.
    """
    n = PAGINATION_PAGE_SIZE + 2
    now = datetime.now(timezone.utc).replace(microsecond=0)
    created_ids: list[str] = []

    try:
        for i in range(n):
            req = CreateEventRequest(
                calendar_id=zoho_calendar_id,
                summary=f"{EVENT_PREFIX} pagination-{i:02d}",
                start=now + timedelta(hours=i + 1),
                end=now + timedelta(hours=i + 1, minutes=30),
            )
            event = await zoho_service.create_event(req)
            created_ids.append(event.event_id)

        collected: list[CalendarEvent] = []
        async for event in zoho_service.list_events(
            zoho_calendar_id,
            time_min=now,
            time_max=now + timedelta(hours=n + 2),
        ):
            if f"{EVENT_PREFIX} pagination-" in (event.summary or ""):
                collected.append(event)

        assert len(collected) >= n, f"Expected at least {n} test events, got {len(collected)}"

    finally:
        for eid in created_ids:
            with suppress(Exception):
                await zoho_service.delete_event(zoho_calendar_id, eid)


# --------------------------------------------------------------------------- #
# Attendees                                                                    #
# --------------------------------------------------------------------------- #


async def test_attendees(zoho_service, zoho_calendar_id, retry_read):
    """Attendees added to a create request survive the Zoho mapper round-trip."""
    from omnidapter.services.calendar.models import Attendee

    now = datetime.now(timezone.utc).replace(microsecond=0)
    req = CreateEventRequest(
        calendar_id=zoho_calendar_id,
        summary=f"{EVENT_PREFIX} attendees test",
        start=now + timedelta(hours=1),
        end=now + timedelta(hours=2),
        attendees=[
            Attendee(email="integration-attendee@example.com", display_name="Test Attendee")
        ],
    )
    event_id: str | None = None

    try:
        created = await zoho_service.create_event(req)
        event_id = created.event_id

        fetched = await retry_read(lambda: zoho_service.get_event(zoho_calendar_id, event_id))
        assert len(fetched.attendees) >= 1
        assert any(a.email == "integration-attendee@example.com" for a in fetched.attendees)

    finally:
        if event_id:
            with suppress(Exception):
                await zoho_service.delete_event(zoho_calendar_id, event_id)
