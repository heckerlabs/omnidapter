"""Integration smoke tests for CalendarApi — verifies routing and error parsing."""

import pytest

from omnidapter_sdk.client import OmnidapterClient
from omnidapter_sdk.exceptions import ApiException
from omnidapter_sdk.models import CreateCalendarRequest, CreateEventRequest
from omnidapter_sdk.models.end import End
from omnidapter_sdk.models.start import Start

pytestmark = pytest.mark.integration

FAKE_CONNECTION = "00000000-0000-0000-0000-000000000000"
FAKE_CALENDAR = "cal_fake"
FAKE_EVENT = "evt_fake"


def test_list_calendars_unknown_connection_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.calendar.list_calendars(FAKE_CONNECTION)
    assert exc_info.value.status == 404


def test_get_calendar_unknown_connection_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.calendar.get_calendar(FAKE_CONNECTION, FAKE_CALENDAR)
    assert exc_info.value.status == 404


def test_create_calendar_unknown_connection_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.calendar.create_calendar(
            FAKE_CONNECTION,
            CreateCalendarRequest(summary="Test Calendar"),
        )
    assert exc_info.value.status == 404


def test_list_events_unknown_connection_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.calendar.list_events(FAKE_CONNECTION, FAKE_CALENDAR)
    assert exc_info.value.status == 404


def test_get_event_unknown_connection_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.calendar.get_event(FAKE_CONNECTION, FAKE_CALENDAR, FAKE_EVENT)
    assert exc_info.value.status == 404


def test_create_event_unknown_connection_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        from datetime import datetime, timezone

        sdk_client.calendar.create_event(
            FAKE_CONNECTION,
            FAKE_CALENDAR,
            CreateEventRequest(
                summary="Test Event",
                start=Start(actual_instance=datetime(2026, 5, 1, 10, 0, 0, tzinfo=timezone.utc)),
                end=End(actual_instance=datetime(2026, 5, 1, 11, 0, 0, tzinfo=timezone.utc)),
            ),
        )
    assert exc_info.value.status == 404
