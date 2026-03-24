"""Unit tests for Zoho calendar service behavior."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from omnidapter.auth.models import OAuth2Credentials
from omnidapter.core.metadata import AuthKind
from omnidapter.providers.zoho.calendar import ZohoCalendarService
from omnidapter.services.calendar.models import EventStatus
from omnidapter.services.calendar.requests import (
    CreateCalendarRequest,
    CreateEventRequest,
    UpdateCalendarRequest,
    UpdateEventRequest,
)
from omnidapter.stores.credentials import StoredCredential


def _stored(access_token: str = "zoho-token") -> StoredCredential:
    return StoredCredential(
        provider_key="zoho",
        auth_kind=AuthKind.OAUTH2,
        credentials=OAuth2Credentials(access_token=access_token),
    )


def _make_service() -> tuple[ZohoCalendarService, AsyncMock]:
    svc = ZohoCalendarService("conn-1", _stored())
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "events": [
            {
                "uid": "evt-1",
                "title": "Updated",
                "dateandtime": {
                    "start": "20240615T100000Z",
                    "end": "20240615T110000Z",
                },
            }
        ]
    }
    svc._http.request = AsyncMock(return_value=mock_response)
    return svc, svc._http.request


class TestStatusValidation:
    async def test_create_non_confirmed_status_rejected(self):
        svc, _ = _make_service()
        with pytest.raises(ValueError, match="confirmed event status"):
            await svc.create_event(
                CreateEventRequest(
                    calendar_id="cal-1",
                    summary="Test",
                    start=datetime(2024, 6, 15, 10, 0, tzinfo=timezone.utc),
                    end=datetime(2024, 6, 15, 11, 0, tzinfo=timezone.utc),
                    status=EventStatus.CANCELLED,
                )
            )

    async def test_update_non_confirmed_status_rejected(self):
        svc, _ = _make_service()
        with pytest.raises(ValueError, match="confirmed event status"):
            await svc.update_event(
                UpdateEventRequest(
                    calendar_id="cal-1",
                    event_id="evt-1",
                    status=EventStatus.TENTATIVE,
                )
            )


class TestUpdateBehavior:
    async def test_update_event_uses_prefetched_event_etag(self):
        svc = ZohoCalendarService("conn-1", _stored())

        get_response = MagicMock()
        get_response.json.return_value = {
            "events": [
                {
                    "uid": "evt-1",
                    "title": "Current",
                    "etag": "etag-123",
                    "dateandtime": {
                        "start": "20240615T100000Z",
                        "end": "20240615T110000Z",
                    },
                }
            ]
        }

        put_response = MagicMock()
        put_response.json.return_value = {
            "events": [
                {
                    "uid": "evt-1",
                    "title": "Updated",
                    "dateandtime": {
                        "start": "20240615T100000Z",
                        "end": "20240615T110000Z",
                    },
                }
            ]
        }

        svc._http.request = AsyncMock(side_effect=[get_response, put_response])

        await svc.update_event(
            UpdateEventRequest(
                calendar_id="cal-1",
                event_id="evt-1",
                summary="Updated",
            )
        )

        assert svc._http.request.await_count == 2
        put_call = svc._http.request.await_args_list[1]
        assert put_call.args[0] == "PUT"
        assert put_call.kwargs["headers"]["ETag"] == "etag-123"


class TestListEvents:
    async def test_list_events_maps_time_bounds_to_zoho_params(self):
        svc = ZohoCalendarService("conn-1", _stored())
        response = MagicMock()
        response.json.return_value = {"events": []}
        svc._http.request = AsyncMock(return_value=response)

        time_min = datetime(2024, 6, 15, 10, 0, tzinfo=timezone.utc)
        time_max = datetime(2024, 6, 15, 12, 0, tzinfo=timezone.utc)

        events = [
            event async for event in svc.list_events("cal-1", time_min=time_min, time_max=time_max)
        ]

        assert events == []
        call = svc._http.request.await_args_list[0]
        assert call.kwargs["params"]["start"] == "20240615T100000Z"
        assert call.kwargs["params"]["end"] == "20240615T120000Z"

    async def test_list_events_filters_results_by_requested_window(self):
        svc = ZohoCalendarService("conn-1", _stored())
        response = MagicMock()
        response.json.return_value = {
            "events": [
                {
                    "uid": "evt-in",
                    "title": "In range",
                    "dateandtime": {
                        "start": "20240615T100000Z",
                        "end": "20240615T110000Z",
                    },
                },
                {
                    "uid": "evt-out",
                    "title": "Out of range",
                    "dateandtime": {
                        "start": "20240615T140000Z",
                        "end": "20240615T150000Z",
                    },
                },
            ]
        }
        svc._http.request = AsyncMock(return_value=response)

        time_min = datetime(2024, 6, 15, 9, 0, tzinfo=timezone.utc)
        time_max = datetime(2024, 6, 15, 12, 0, tzinfo=timezone.utc)

        events = [
            event async for event in svc.list_events("cal-1", time_min=time_min, time_max=time_max)
        ]

        assert [event.event_id for event in events] == ["evt-in"]


class TestCalendarCrud:
    async def test_create_calendar_posts_expected_payload(self):
        svc, mock_request = _make_service()
        mock_request.return_value.json.return_value = {
            "calendars": [
                {
                    "uid": "cal-2",
                    "name": "Team",
                    "timezone": "UTC",
                }
            ]
        }

        created = await svc.create_calendar(
            CreateCalendarRequest(summary="Team", timezone="UTC", extra={"isprivate": True})
        )

        call = mock_request.await_args_list[-1]
        assert call.args[0] == "POST"
        assert call.args[1].endswith("/calendars")
        assert "calendarData" in call.kwargs["params"]
        assert created.calendar_id == "cal-2"

    async def test_update_calendar_puts_expected_payload(self):
        svc, mock_request = _make_service()
        mock_request.return_value.json.return_value = {
            "calendars": [
                {
                    "uid": "cal-2",
                    "name": "Renamed",
                    "timezone": "UTC",
                }
            ]
        }

        updated = await svc.update_calendar(
            UpdateCalendarRequest(calendar_id="cal-2", summary="Renamed")
        )

        call = mock_request.await_args_list[-1]
        assert call.args[0] == "PUT"
        assert call.args[1].endswith("/calendars/cal-2")
        assert "calendarData" in call.kwargs["params"]
        assert updated.summary == "Renamed"
