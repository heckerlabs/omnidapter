"""
Unit tests for omnidapter.providers.google.calendar.GoogleCalendarService.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from omnidapter.auth.models import OAuth2Credentials
from omnidapter.core.metadata import AuthKind
from omnidapter.providers.google.calendar import GoogleCalendarService
from omnidapter.services.calendar.models import EventStatus
from omnidapter.services.calendar.requests import UpdateEventRequest
from omnidapter.stores.credentials import StoredCredential


def _google_stored() -> StoredCredential:
    return StoredCredential(
        provider_key="google",
        auth_kind=AuthKind.OAUTH2,
        credentials=OAuth2Credentials(access_token="test-token"),
    )


def _make_service() -> tuple[GoogleCalendarService, AsyncMock]:
    svc = GoogleCalendarService("conn-1", _google_stored())
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "id": "evt-1",
        "summary": "Updated",
        "start": {"dateTime": "2024-06-15T10:00:00Z"},
        "end": {"dateTime": "2024-06-15T11:00:00Z"},
    }
    svc._http.request = AsyncMock(return_value=mock_response)
    return svc, svc._http.request


class TestUpdateEventStatusSerialization:
    async def test_status_sent_as_plain_string(self):
        """EventStatus enum must be serialized to its string value, not the enum object."""
        svc, mock_request = _make_service()
        await svc.update_event(
            UpdateEventRequest(
                calendar_id="cal-1",
                event_id="evt-1",
                status=EventStatus.TENTATIVE,
            )
        )
        _, kwargs = mock_request.call_args
        body = kwargs["json"]
        assert body["status"] == "tentative"
        assert isinstance(body["status"], str)
        assert not isinstance(body["status"], EventStatus)

    async def test_cancelled_status_sent_as_plain_string(self):
        svc, mock_request = _make_service()
        await svc.update_event(
            UpdateEventRequest(
                calendar_id="cal-1",
                event_id="evt-1",
                status=EventStatus.CANCELLED,
            )
        )
        _, kwargs = mock_request.call_args
        body = kwargs["json"]
        assert body["status"] == "cancelled"
        assert isinstance(body["status"], str)

    async def test_none_status_omitted_from_body(self):
        svc, mock_request = _make_service()
        await svc.update_event(
            UpdateEventRequest(
                calendar_id="cal-1",
                event_id="evt-1",
                summary="No status change",
            )
        )
        _, kwargs = mock_request.call_args
        body = kwargs["json"]
        assert "status" not in body
