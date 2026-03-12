"""
Integration tests for Zoho Calendar.

Required env vars:
    OMNIDAPTER_INTEGRATION=1
    OMNIDAPTER_TEST_ZOHO_CLIENT_ID
    OMNIDAPTER_TEST_ZOHO_CLIENT_SECRET
    OMNIDAPTER_TEST_ZOHO_REFRESH_TOKEN

Optional:
    OMNIDAPTER_TEST_ZOHO_CALENDAR_ID   (defaults to first calendar on the account)
    OMNIDAPTER_TEST_ATTENDEE_EMAIL     (comma-separated invitee emails for attendee tests)

Use a dedicated test Zoho account. Tests create and delete events but never
touch data they did not create.

Notes on Zoho limitations:
  - No availability (free/busy) endpoint in the API.
  - No webhook / push-notification support.
  - The Zoho API wraps events in {"events": [...]} envelopes; the mapper
    must handle both create/update responses and get/list responses.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import suppress
from datetime import datetime, timedelta, timezone

import pytest
from omnidapter.auth.models import OAuth2Credentials
from omnidapter.services.calendar.models import CalendarEvent, EventStatus
from omnidapter.services.calendar.requests import CreateEventRequest, UpdateEventRequest

from .conftest import EVENT_PREFIX, PAGINATION_PAGE_SIZE, _require_env, _stale_oauth2_stored

pytestmark = pytest.mark.integration


async def _assert_deleted_event_state(zoho_service, calendar_id: str, event_id: str) -> None:
    from omnidapter.core.errors import ProviderAPIError

    last_status: EventStatus | None = None
    for attempt in range(3):
        try:
            deleted = await zoho_service.get_event(calendar_id, event_id)
        except ProviderAPIError as exc:
            assert exc.status_code in (400, 404)
            return

        if deleted.status in (EventStatus.CANCELLED, EventStatus.UNKNOWN):
            return

        last_status = deleted.status
        if attempt < 2:
            await asyncio.sleep(1)

    pytest.fail(f"Deleted event still readable with status={last_status!r}")


# --------------------------------------------------------------------------- #
# Token refresh                                                                #
# --------------------------------------------------------------------------- #


async def test_token_refresh():
    """
    Expired access token + valid refresh token → fresh credentials that work.
    """
    from omnidapter.providers.zoho.provider import ZohoProvider

    _require_env(
        "OMNIDAPTER_TEST_ZOHO_CLIENT_ID",
        "OMNIDAPTER_TEST_ZOHO_CLIENT_SECRET",
        "OMNIDAPTER_TEST_ZOHO_REFRESH_TOKEN",
    )

    stale = _stale_oauth2_stored("zoho", os.environ["OMNIDAPTER_TEST_ZOHO_REFRESH_TOKEN"])
    stale_creds = stale.credentials
    assert isinstance(stale_creds, OAuth2Credentials)
    assert stale_creds.is_expired()

    provider = ZohoProvider(
        client_id=os.environ["OMNIDAPTER_TEST_ZOHO_CLIENT_ID"],
        client_secret=os.environ["OMNIDAPTER_TEST_ZOHO_CLIENT_SECRET"],
    )
    refreshed = await provider.refresh_token(stale)

    new_creds = refreshed.credentials
    assert isinstance(new_creds, OAuth2Credentials)
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

        await _assert_deleted_event_state(zoho_service, zoho_calendar_id, created.event_id)

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


async def test_list_events_time_window_filters(zoho_service, zoho_calendar_id):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    near_req = CreateEventRequest(
        calendar_id=zoho_calendar_id,
        summary=f"{EVENT_PREFIX} list-window-near",
        start=now + timedelta(hours=2),
        end=now + timedelta(hours=3),
    )
    far_req = CreateEventRequest(
        calendar_id=zoho_calendar_id,
        summary=f"{EVENT_PREFIX} list-window-far",
        start=now + timedelta(days=14),
        end=now + timedelta(days=14, hours=1),
    )
    near_event_id: str | None = None
    far_event_id: str | None = None

    try:
        near = await zoho_service.create_event(near_req)
        far = await zoho_service.create_event(far_req)
        near_event_id = near.event_id
        far_event_id = far.event_id

        seen_ids: set[str] = set()
        async for event in zoho_service.list_events(
            zoho_calendar_id,
            time_min=now + timedelta(hours=1),
            time_max=now + timedelta(hours=6),
        ):
            if (near_event_id and event.event_id == near_event_id) or (
                far_event_id and event.event_id == far_event_id
            ):
                seen_ids.add(event.event_id)

        assert near_event_id in seen_ids
        assert far_event_id not in seen_ids
    finally:
        if near_event_id:
            with suppress(Exception):
                await zoho_service.delete_event(zoho_calendar_id, near_event_id)
        if far_event_id:
            with suppress(Exception):
                await zoho_service.delete_event(zoho_calendar_id, far_event_id)


# --------------------------------------------------------------------------- #
# Attendees                                                                    #
# --------------------------------------------------------------------------- #


async def test_attendees(zoho_service, zoho_calendar_id, retry_read, integration_attendee_emails):
    """Attendees added to a create request survive the Zoho mapper round-trip."""
    from omnidapter.services.calendar.models import Attendee

    now = datetime.now(timezone.utc).replace(microsecond=0)
    req = CreateEventRequest(
        calendar_id=zoho_calendar_id,
        summary=f"{EVENT_PREFIX} attendees test",
        start=now + timedelta(hours=1),
        end=now + timedelta(hours=2),
        attendees=[
            Attendee(email=email, display_name=f"Test Attendee {idx + 1}")
            for idx, email in enumerate(integration_attendee_emails)
        ],
    )
    event_id: str | None = None

    try:
        created = await zoho_service.create_event(req)
        event_id = created.event_id

        fetched = await retry_read(lambda: zoho_service.get_event(zoho_calendar_id, event_id))
        assert len(fetched.attendees) >= 1
        fetched_emails = {a.email.lower().removeprefix("mailto:") for a in fetched.attendees}
        expected_emails = {
            email.lower().removeprefix("mailto:") for email in integration_attendee_emails
        }
        assert expected_emails.issubset(fetched_emails)

    finally:
        if event_id:
            with suppress(Exception):
                await zoho_service.delete_event(zoho_calendar_id, event_id)


async def test_all_day_event(zoho_service, zoho_calendar_id, retry_read):
    now = datetime.now(timezone.utc)
    req = CreateEventRequest(
        calendar_id=zoho_calendar_id,
        summary=f"{EVENT_PREFIX} all-day",
        start=now.date() + timedelta(days=1),
        end=now.date() + timedelta(days=2),
        all_day=True,
    )
    event_id: str | None = None

    try:
        created = await zoho_service.create_event(req)
        event_id = created.event_id
        fetched = await retry_read(lambda: zoho_service.get_event(zoho_calendar_id, event_id))
        assert fetched.all_day is True
    finally:
        if event_id:
            with suppress(Exception):
                await zoho_service.delete_event(zoho_calendar_id, event_id)


async def test_get_event_unknown_id_raises(zoho_service, zoho_calendar_id):
    from omnidapter.core.errors import ProviderAPIError

    with pytest.raises(ProviderAPIError) as exc_info:
        await zoho_service.get_event(zoho_calendar_id, "non-existent-omnidapter-event")
    assert exc_info.value.status_code in (400, 404)


async def test_non_confirmed_status_rejected(zoho_service, zoho_calendar_id):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    with pytest.raises(ValueError, match="confirmed event status"):
        await zoho_service.create_event(
            CreateEventRequest(
                calendar_id=zoho_calendar_id,
                summary=f"{EVENT_PREFIX} rejected status",
                start=now + timedelta(hours=1),
                end=now + timedelta(hours=2),
                status=EventStatus.CANCELLED,
            )
        )
