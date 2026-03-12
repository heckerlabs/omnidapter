"""Unit tests for CalDAV calendar-level CRUD helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from omnidapter.auth.models import BasicCredentials
from omnidapter.core.metadata import AuthKind
from omnidapter.providers.caldav.calendar import CalDAVCalendarService
from omnidapter.services.calendar.requests import CreateCalendarRequest, UpdateCalendarRequest
from omnidapter.stores.credentials import StoredCredential


def _stored() -> StoredCredential:
    return StoredCredential(
        provider_key="caldav",
        auth_kind=AuthKind.BASIC,
        credentials=BasicCredentials(username="user", password="pw"),
        provider_config={"server_url": "https://dav.example.com/caldav/user"},
    )


def _make_service() -> tuple[CalDAVCalendarService, AsyncMock]:
    svc = CalDAVCalendarService("conn-1", _stored())
    svc._http.request = AsyncMock(return_value=MagicMock(text="", json=MagicMock(return_value={})))
    return svc, svc._http.request


class TestCalendarCrud:
    async def test_create_calendar_uses_mkcalendar(self):
        svc, mock_request = _make_service()
        svc.list_calendars = AsyncMock(
            return_value=[
                MagicMock(
                    calendar_id="/caldav/user/existing/", summary="existing", description=None
                )
            ]
        )
        svc.get_calendar = AsyncMock(return_value=MagicMock(calendar_id="/caldav/user/new/"))

        await svc.create_calendar(CreateCalendarRequest(summary="New Team"))

        call = mock_request.await_args_list[0]
        assert call.args[0] == "MKCALENDAR"

    async def test_update_calendar_uses_proppatch(self):
        svc, mock_request = _make_service()
        svc.get_calendar = AsyncMock(return_value=MagicMock(calendar_id="/caldav/user/existing/"))

        await svc.update_calendar(
            UpdateCalendarRequest(calendar_id="/caldav/user/existing/", summary="Renamed")
        )

        call = mock_request.await_args_list[0]
        assert call.args[0] == "PROPPATCH"

    async def test_delete_calendar_uses_delete(self):
        svc, mock_request = _make_service()
        await svc.delete_calendar("/caldav/user/existing/")

        call = mock_request.await_args_list[0]
        assert call.args[0] == "DELETE"
