"""Unit tests for CalDAV calendar-level CRUD helpers."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from unittest.mock import AsyncMock, MagicMock

from omnidapter.auth.models import BasicCredentials
from omnidapter.core.metadata import AuthKind
from omnidapter.providers.caldav.calendar import CalDAVCalendarService
from omnidapter.providers.caldav.provider import CalDAVProvider
from omnidapter.providers.caldav.server_hints import (
    CalDAVServerHint,
    detect_server_hint,
    get_principal_url_template,
)
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

    async def test_create_calendar_escapes_xml_values(self):
        svc, mock_request = _make_service()
        svc.list_calendars = AsyncMock(
            return_value=[
                MagicMock(
                    calendar_id="/caldav/user/existing/", summary="existing", description=None
                )
            ]
        )
        svc.get_calendar = AsyncMock(return_value=MagicMock(calendar_id="/caldav/user/new/"))

        await svc.create_calendar(
            CreateCalendarRequest(summary="A & B <Team>", description="x < y & z")
        )

        call = mock_request.await_args_list[0]
        body = call.kwargs["data"].decode()
        assert "A &amp; B &lt;Team&gt;" in body
        assert "x &lt; y &amp; z" in body
        ET.fromstring(body)

    async def test_update_calendar_uses_proppatch(self):
        svc, mock_request = _make_service()
        svc.get_calendar = AsyncMock(return_value=MagicMock(calendar_id="/caldav/user/existing/"))

        await svc.update_calendar(
            UpdateCalendarRequest(calendar_id="/caldav/user/existing/", summary="Renamed")
        )

        call = mock_request.await_args_list[0]
        assert call.args[0] == "PROPPATCH"

    async def test_update_calendar_escapes_xml_values(self):
        svc, mock_request = _make_service()
        svc.get_calendar = AsyncMock(return_value=MagicMock(calendar_id="/caldav/user/existing/"))

        await svc.update_calendar(
            UpdateCalendarRequest(
                calendar_id="/caldav/user/existing/",
                summary="A & B <Team>",
                description="x < y & z",
            )
        )

        call = mock_request.await_args_list[0]
        body = call.kwargs["data"].decode()
        assert "A &amp; B &lt;Team&gt;" in body
        assert "x &lt; y &amp; z" in body
        ET.fromstring(body)

    async def test_delete_calendar_uses_delete(self):
        svc, mock_request = _make_service()
        await svc.delete_calendar("/caldav/user/existing/")

        call = mock_request.await_args_list[0]
        assert call.args[0] == "DELETE"


# ---------------------------------------------------------------------------
# CalDAVProvider
# ---------------------------------------------------------------------------


class TestCalDAVProvider:
    def test_metadata(self) -> None:
        assert CalDAVProvider().metadata.provider_key == "caldav"

    def test_get_oauth_config_returns_none(self) -> None:
        assert CalDAVProvider().get_oauth_config() is None

    def test_get_calendar_service_returns_service(self) -> None:
        from omnidapter.auth.models import BasicCredentials
        from omnidapter.core.metadata import AuthKind
        from omnidapter.providers.caldav.calendar import CalDAVCalendarService
        from omnidapter.stores.credentials import StoredCredential

        stored = StoredCredential(
            provider_key="caldav",
            auth_kind=AuthKind.BASIC,
            credentials=BasicCredentials(username="u", password="p"),
            provider_config={"server_url": "https://dav.example.com/"},
        )
        svc = CalDAVProvider().get_calendar_service("conn-1", stored)
        assert isinstance(svc, CalDAVCalendarService)


# ---------------------------------------------------------------------------
# detect_server_hint
# ---------------------------------------------------------------------------


class TestDetectServerHint:
    def test_icloud(self) -> None:
        assert detect_server_hint("https://caldav.icloud.com") == CalDAVServerHint.ICLOUD

    def test_fastmail(self) -> None:
        assert detect_server_hint("https://caldav.fastmail.com/dav/") == CalDAVServerHint.FASTMAIL

    def test_fastmail_fm(self) -> None:
        assert detect_server_hint("https://caldav.fastmail.fm/") == CalDAVServerHint.FASTMAIL

    def test_nextcloud_keyword(self) -> None:
        assert (
            detect_server_hint("https://cloud.example.com/nextcloud/remote.php/dav")
            == CalDAVServerHint.NEXTCLOUD
        )

    def test_nextcloud_path(self) -> None:
        assert (
            detect_server_hint("https://cloud.example.com/remote.php/dav")
            == CalDAVServerHint.NEXTCLOUD
        )

    def test_google(self) -> None:
        assert (
            detect_server_hint("https://apidata.google.com/caldav/v2/") == CalDAVServerHint.GOOGLE
        )

    def test_radicale(self) -> None:
        assert detect_server_hint("https://radicale.example.com/") == CalDAVServerHint.RADICALE

    def test_davical(self) -> None:
        assert detect_server_hint("https://davical.example.com/") == CalDAVServerHint.DAVICAL

    def test_generic_fallback(self) -> None:
        assert detect_server_hint("https://dav.example.com/caldav/") == CalDAVServerHint.GENERIC


# ---------------------------------------------------------------------------
# get_principal_url_template
# ---------------------------------------------------------------------------


class TestGetPrincipalUrlTemplate:
    def test_icloud(self) -> None:
        url = get_principal_url_template(
            CalDAVServerHint.ICLOUD, "https://caldav.icloud.com", "user@example.com"
        )
        assert url == "https://caldav.icloud.com"

    def test_nextcloud(self) -> None:
        url = get_principal_url_template(
            CalDAVServerHint.NEXTCLOUD, "https://cloud.example.com", "alice"
        )
        assert url == "https://cloud.example.com/remote.php/dav/principals/users/alice/"

    def test_fastmail(self) -> None:
        url = get_principal_url_template(
            CalDAVServerHint.FASTMAIL, "https://caldav.fastmail.com/dav", "user@example.com"
        )
        assert url == "https://caldav.fastmail.com/dav/"

    def test_generic(self) -> None:
        url = get_principal_url_template(
            CalDAVServerHint.GENERIC, "https://dav.example.com/caldav", "user"
        )
        assert url == "https://dav.example.com/caldav/"
