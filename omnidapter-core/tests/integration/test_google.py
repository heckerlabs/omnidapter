"""
Integration tests for Google Calendar.

Required env vars:
    OMNIDAPTER_TEST_GOOGLE_CLIENT_ID
    OMNIDAPTER_TEST_GOOGLE_CLIENT_SECRET
    OMNIDAPTER_TEST_GOOGLE_REFRESH_TOKEN

Optional:
    OMNIDAPTER_TEST_GOOGLE_CALENDAR_ID   (defaults to first calendar on the account)
    OMNIDAPTER_TEST_ATTENDEE_EMAIL       (comma-separated invitee emails for attendee tests)

Use a dedicated test Google account. Tests create and delete events but never
touch data they did not create.
"""

from __future__ import annotations

import os
from contextlib import suppress
from datetime import date, datetime, timedelta, timezone

import pytest
from omnidapter.auth.models import OAuth2Credentials
from omnidapter.services.calendar.models import (
    Attendee,
    CalendarEvent,
    EventStatus,
    EventVisibility,
    Recurrence,
    Reminder,
    ReminderOverride,
)
from omnidapter.services.calendar.requests import (
    CreateCalendarRequest,
    CreateEventRequest,
    GetAvailabilityRequest,
    UpdateCalendarRequest,
    UpdateEventRequest,
)

from .conftest import EVENT_PREFIX, PAGINATION_PAGE_SIZE, _require_env, _stale_oauth2_stored


async def _assert_deleted_event_state(google_service, calendar_id: str, event_id: str) -> None:
    """Google may return 404/410 or a cancelled tombstone after delete."""
    from omnidapter.core.errors import ProviderAPIError

    try:
        deleted = await google_service.get_event(calendar_id, event_id)
    except ProviderAPIError as exc:
        assert exc.status_code in (404, 410)
        return

    assert deleted.status == EventStatus.CANCELLED


# --------------------------------------------------------------------------- #
# Token refresh                                                                #
# --------------------------------------------------------------------------- #


async def test_token_refresh():
    """
    Expired access token + valid refresh token → fresh credentials that work.

    This is the single end-to-end test for the OAuth2 token refresh path.
    """
    from omnidapter.providers.google.provider import GoogleProvider

    _require_env(
        "OMNIDAPTER_TEST_GOOGLE_CLIENT_ID",
        "OMNIDAPTER_TEST_GOOGLE_CLIENT_SECRET",
        "OMNIDAPTER_TEST_GOOGLE_REFRESH_TOKEN",
    )

    stale = _stale_oauth2_stored("google", os.environ["OMNIDAPTER_TEST_GOOGLE_REFRESH_TOKEN"])
    stale_creds = stale.credentials
    assert isinstance(stale_creds, OAuth2Credentials)
    assert stale_creds.is_expired(), "Fixture must start with an expired token"

    provider = GoogleProvider(
        client_id=os.environ["OMNIDAPTER_TEST_GOOGLE_CLIENT_ID"],
        client_secret=os.environ["OMNIDAPTER_TEST_GOOGLE_CLIENT_SECRET"],
    )
    refreshed = await provider.refresh_token(stale)

    new_creds = refreshed.credentials
    assert isinstance(new_creds, OAuth2Credentials)
    assert new_creds.access_token
    assert new_creds.access_token != "stale-will-be-refreshed"
    assert not new_creds.is_expired()

    # Verify the new token is actually accepted by the API.
    from omnidapter.core.metadata import ServiceKind

    svc = provider.get_service(ServiceKind.CALENDAR, "test-token-refresh", refreshed)
    calendars = await svc.list_calendars()
    assert len(calendars) >= 1


# --------------------------------------------------------------------------- #
# Calendar discovery                                                           #
# --------------------------------------------------------------------------- #


async def test_list_calendars(google_service):
    """list_calendars() returns at least one Calendar with required fields."""
    calendars = await google_service.list_calendars()
    assert len(calendars) >= 1
    for cal in calendars:
        assert cal.calendar_id
        assert isinstance(cal.summary, str)


async def test_calendar_crud_round_trip(google_service):
    created_id: str | None = None
    try:
        created = await google_service.create_calendar(
            CreateCalendarRequest(summary=f"{EVENT_PREFIX} calendar crud", timezone="UTC")
        )
        created_id = created.calendar_id
        assert created.calendar_id
        assert created.summary

        fetched = await google_service.get_calendar(created.calendar_id)
        assert fetched.calendar_id == created.calendar_id

        updated = await google_service.update_calendar(
            UpdateCalendarRequest(
                calendar_id=created.calendar_id, summary=f"{EVENT_PREFIX} renamed"
            )
        )
        assert updated.summary == f"{EVENT_PREFIX} renamed"

        await google_service.delete_calendar(created.calendar_id)
        created_id = None
    finally:
        if created_id:
            with suppress(Exception):
                await google_service.delete_calendar(created_id)


# --------------------------------------------------------------------------- #
# CRUD round-trip                                                              #
# --------------------------------------------------------------------------- #


async def test_crud_round_trip(google_service, google_calendar_id, retry_read):
    """
    Create → read → update → delete with field-level assertions at each step.
    Verifies that HTTP construction, auth headers, and mappers all work together.
    """
    now = datetime.now(timezone.utc).replace(microsecond=0)
    created_ids: list[str] = []

    try:
        # ── Create ──────────────────────────────────────────────────────────
        req = CreateEventRequest(
            calendar_id=google_calendar_id,
            summary=f"{EVENT_PREFIX} crud round-trip",
            start=now + timedelta(hours=1),
            end=now + timedelta(hours=2),
            description="Integration test event — please ignore",
            location="42 Integration Lane",
        )
        created = await google_service.create_event(req)
        created_ids.append(created.event_id)

        assert created.event_id
        assert created.summary == req.summary
        assert created.calendar_id == google_calendar_id

        # ── Read back ────────────────────────────────────────────────────────
        fetched = await retry_read(
            lambda: google_service.get_event(google_calendar_id, created.event_id)
        )
        assert fetched.summary == req.summary
        assert fetched.description == req.description
        assert fetched.location == req.location
        assert isinstance(fetched.start, datetime)
        assert isinstance(fetched.end, datetime)

        # ── Update ───────────────────────────────────────────────────────────
        update_req = UpdateEventRequest(
            calendar_id=google_calendar_id,
            event_id=created.event_id,
            summary=f"{EVENT_PREFIX} crud round-trip (updated)",
            description="Updated by integration test",
        )
        updated = await google_service.update_event(update_req)
        assert updated.summary == update_req.summary

        fetched_after_update = await retry_read(
            lambda: google_service.get_event(google_calendar_id, created.event_id)
        )
        assert fetched_after_update.summary == update_req.summary
        assert fetched_after_update.description == update_req.description

        # ── Delete ───────────────────────────────────────────────────────────
        await google_service.delete_event(google_calendar_id, created.event_id)
        created_ids.remove(created.event_id)

        await _assert_deleted_event_state(google_service, google_calendar_id, created.event_id)

    finally:
        for eid in created_ids:
            with suppress(Exception):
                await google_service.delete_event(google_calendar_id, eid)


# --------------------------------------------------------------------------- #
# Mapper fidelity                                                              #
# --------------------------------------------------------------------------- #


async def test_mapper_fidelity(
    google_service, google_calendar_id, retry_read, integration_attendee_emails
):
    """
    Verify that the Google → CalendarEvent mapper correctly handles real
    response shapes, including metadata fields the API adds (created_at,
    updated_at, ical_uid, html_link, etag, sequence).
    """
    now = datetime.now(timezone.utc).replace(microsecond=0)
    req = CreateEventRequest(
        calendar_id=google_calendar_id,
        summary=f"{EVENT_PREFIX} mapper fidelity",
        start=now + timedelta(hours=1),
        end=now + timedelta(hours=2),
        description="Testing field-mapping fidelity",
        location="Mapper Test Location",
        timezone="UTC",
        attendees=[
            Attendee(email=email, display_name=f"Test Attendee {idx + 1}")
            for idx, email in enumerate(integration_attendee_emails)
        ],
    )
    event_id: str | None = None

    try:
        created = await google_service.create_event(req)
        event_id = created.event_id

        fetched = await retry_read(lambda: google_service.get_event(google_calendar_id, event_id))

        assert isinstance(fetched, CalendarEvent)
        assert fetched.event_id
        assert fetched.calendar_id == google_calendar_id
        assert fetched.summary == req.summary
        assert fetched.description == req.description
        assert fetched.location == req.location
        assert isinstance(fetched.start, datetime)
        assert isinstance(fetched.end, datetime)
        # API-provided metadata
        assert fetched.status in EventStatus
        assert fetched.visibility in EventVisibility
        assert fetched.created_at is not None
        assert fetched.updated_at is not None
        assert fetched.ical_uid is not None
        assert fetched.html_link is not None
        assert fetched.etag is not None
        assert fetched.sequence is not None
        # Attendees round-trip
        assert len(fetched.attendees) >= 1
        fetched_emails = {a.email.lower().removeprefix("mailto:") for a in fetched.attendees}
        expected_emails = {
            email.lower().removeprefix("mailto:") for email in integration_attendee_emails
        }
        assert expected_emails.issubset(fetched_emails)

    finally:
        if event_id:
            with suppress(Exception):
                await google_service.delete_event(google_calendar_id, event_id)


# --------------------------------------------------------------------------- #
# All-day event mapper                                                         #
# --------------------------------------------------------------------------- #


async def test_all_day_event(google_service, google_calendar_id, retry_read):
    """All-day events use date (not datetime) in start/end; verify mapper handles this."""
    today = datetime.now(timezone.utc).date()
    req = CreateEventRequest(
        calendar_id=google_calendar_id,
        summary=f"{EVENT_PREFIX} all-day event",
        start=today + timedelta(days=1),
        end=today + timedelta(days=2),
        all_day=True,
    )
    event_id: str | None = None

    try:
        created = await google_service.create_event(req)
        event_id = created.event_id

        fetched = await retry_read(lambda: google_service.get_event(google_calendar_id, event_id))
        assert fetched.all_day is True
        assert isinstance(fetched.start, date)
        assert not isinstance(fetched.start, datetime)

    finally:
        if event_id:
            with suppress(Exception):
                await google_service.delete_event(google_calendar_id, event_id)


# --------------------------------------------------------------------------- #
# Pagination                                                                   #
# --------------------------------------------------------------------------- #


async def test_pagination(google_service, google_calendar_id):
    """
    Create PAGINATION_PAGE_SIZE + 2 events, list them with page_size=PAGINATION_PAGE_SIZE,
    and verify all events are returned across pages.
    """
    n = PAGINATION_PAGE_SIZE + 2
    now = datetime.now(timezone.utc).replace(microsecond=0)
    created_ids: list[str] = []

    try:
        for i in range(n):
            req = CreateEventRequest(
                calendar_id=google_calendar_id,
                summary=f"{EVENT_PREFIX} pagination-{i:02d}",
                start=now + timedelta(hours=i + 1),
                end=now + timedelta(hours=i + 1, minutes=30),
            )
            event = await google_service.create_event(req)
            created_ids.append(event.event_id)

        # Collect via the auto-paginated iterator.
        collected: list[CalendarEvent] = []
        async for event in google_service.list_events(
            google_calendar_id,
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
                await google_service.delete_event(google_calendar_id, eid)


# --------------------------------------------------------------------------- #
# Availability (free/busy)                                                     #
# --------------------------------------------------------------------------- #


async def test_get_availability(google_service, google_calendar_id):
    """get_availability() returns a well-formed AvailabilityResponse."""
    now = datetime.now(timezone.utc)
    req = GetAvailabilityRequest(
        calendar_ids=[google_calendar_id],
        time_min=now,
        time_max=now + timedelta(days=7),
    )
    result = await google_service.get_availability(req)

    assert result.queried_calendars == [google_calendar_id]
    assert result.time_min == req.time_min
    assert result.time_max == req.time_max
    assert isinstance(result.busy_intervals, list)
    for interval in result.busy_intervals:
        assert isinstance(interval.start, datetime)
        assert isinstance(interval.end, datetime)
        assert interval.start < interval.end


async def test_status_visibility_round_trip(google_service, google_calendar_id, retry_read):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    req = CreateEventRequest(
        calendar_id=google_calendar_id,
        summary=f"{EVENT_PREFIX} status visibility",
        start=now + timedelta(hours=3),
        end=now + timedelta(hours=4),
        status=EventStatus.TENTATIVE,
        visibility=EventVisibility.PRIVATE.value,
    )
    event_id: str | None = None

    try:
        created = await google_service.create_event(req)
        event_id = created.event_id
        fetched = await retry_read(lambda: google_service.get_event(google_calendar_id, event_id))
        assert fetched.status in (EventStatus.TENTATIVE, EventStatus.CONFIRMED)
        assert fetched.visibility == EventVisibility.PRIVATE
    finally:
        if event_id:
            with suppress(Exception):
                await google_service.delete_event(google_calendar_id, event_id)


async def test_reminders_round_trip(google_service, google_calendar_id, retry_read):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    req = CreateEventRequest(
        calendar_id=google_calendar_id,
        summary=f"{EVENT_PREFIX} reminders",
        start=now + timedelta(hours=5),
        end=now + timedelta(hours=6),
        reminders=Reminder(
            use_default=False,
            overrides=[ReminderOverride(method="popup", minutes_before=10)],
        ),
    )
    event_id: str | None = None

    try:
        created = await google_service.create_event(req)
        event_id = created.event_id
        fetched = await retry_read(lambda: google_service.get_event(google_calendar_id, event_id))
        assert fetched.reminders is not None
        assert fetched.reminders.use_default is False
        assert fetched.reminders.overrides
        assert fetched.reminders.overrides[0].minutes_before == 10
    finally:
        if event_id:
            with suppress(Exception):
                await google_service.delete_event(google_calendar_id, event_id)


async def test_get_event_unknown_id_raises(google_service, google_calendar_id):
    from omnidapter.core.errors import ProviderAPIError

    with pytest.raises(ProviderAPIError) as exc_info:
        await google_service.get_event(google_calendar_id, "non-existent-omnidapter-event")
    assert exc_info.value.status_code in (400, 404)


# --------------------------------------------------------------------------- #
# Recurrence                                                                   #
# --------------------------------------------------------------------------- #


async def test_recurring_event(google_service, google_calendar_id, retry_read):
    """Create a recurring event and verify recurrence rules survive the mapper."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    req = CreateEventRequest(
        calendar_id=google_calendar_id,
        summary=f"{EVENT_PREFIX} recurring weekly",
        start=now + timedelta(hours=1),
        end=now + timedelta(hours=2),
        timezone="UTC",
        recurrence=Recurrence(rules=["RRULE:FREQ=WEEKLY;COUNT=4"]),
    )
    event_id: str | None = None

    try:
        created = await google_service.create_event(req)
        event_id = created.event_id

        fetched = await retry_read(lambda: google_service.get_event(google_calendar_id, event_id))
        assert fetched.recurrence is not None
        assert any("RRULE" in rule for rule in fetched.recurrence.rules)

    finally:
        if event_id:
            with suppress(Exception):
                await google_service.delete_event(google_calendar_id, event_id)
