"""Unit tests for Zoho calendar service behavior."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from omnidapter.auth.models import OAuth2Credentials
from omnidapter.core.metadata import AuthKind
from omnidapter.providers.zoho.calendar import ZohoCalendarService
from omnidapter.services.calendar.models import EventStatus
from omnidapter.services.calendar.requests import CreateEventRequest, UpdateEventRequest
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
