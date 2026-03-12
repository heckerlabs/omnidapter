"""
Unit tests for the Apple Calendar provider.

Verifies Apple-specific behaviour: the iCloud server URL is injected
automatically, the server hint is set to ICLOUD, and the provider key
is "apple" — all without the caller supplying a server_url config field.
"""

from __future__ import annotations

import pytest
from omnidapter.auth.models import BasicCredentials
from omnidapter.core.errors import InvalidCredentialFormatError
from omnidapter.core.metadata import AuthKind
from omnidapter.providers.apple.calendar import ICLOUD_CALDAV_URL, AppleCalendarService
from omnidapter.providers.apple.metadata import APPLE_METADATA
from omnidapter.providers.apple.provider import AppleProvider
from omnidapter.providers.caldav.calendar import CalDAVCalendarService
from omnidapter.providers.caldav.server_hints import CalDAVServerHint
from omnidapter.stores.credentials import StoredCredential


def _apple_stored(provider_config: dict | None = None) -> StoredCredential:
    return StoredCredential(
        provider_key="apple",
        auth_kind=AuthKind.BASIC,
        credentials=BasicCredentials(username="user@icloud.com", password="app-specific-pw"),
        provider_config=provider_config,
    )


class TestAppleCalendarService:
    def test_server_url_is_icloud(self):
        svc = AppleCalendarService("conn-1", _apple_stored())
        assert svc._server_url == ICLOUD_CALDAV_URL

    def test_server_url_ignores_provider_config(self):
        """server_url in provider_config must not override the iCloud URL."""
        svc = AppleCalendarService(
            "conn-1", _apple_stored(provider_config={"server_url": "https://other.example.com"})
        )
        assert svc._server_url == ICLOUD_CALDAV_URL

    def test_server_hint_is_icloud(self):
        svc = AppleCalendarService("conn-1", _apple_stored())
        assert svc._server_hint == CalDAVServerHint.ICLOUD

    def test_provider_key(self):
        svc = AppleCalendarService("conn-1", _apple_stored())
        assert svc._provider_key == "apple"

    def test_http_client_provider_key(self):
        svc = AppleCalendarService("conn-1", _apple_stored())
        assert svc._http._provider_key == "apple"

    def test_capabilities_match_metadata(self):
        svc = AppleCalendarService("conn-1", _apple_stored())
        meta_caps = set(APPLE_METADATA.capabilities.get("calendar", []))
        svc_caps = {c.value for c in svc.capabilities}
        assert svc_caps == meta_caps


class TestAppleProvider:
    def test_metadata_provider_key(self):
        assert AppleProvider().metadata.provider_key == "apple"

    def test_metadata_display_name(self):
        assert AppleProvider().metadata.display_name

    def test_no_oauth(self):
        assert AppleProvider().get_oauth_config() is None

    def test_get_calendar_service_returns_apple_service(self):
        provider = AppleProvider()
        stored = _apple_stored()
        svc = provider.get_calendar_service("conn-1", stored)
        assert isinstance(svc, AppleCalendarService)

    def test_get_calendar_service_passes_connection_id(self):
        provider = AppleProvider()
        stored = _apple_stored()
        svc = provider.get_calendar_service("my-conn", stored)
        assert svc._connection_id == "my-conn"

    def test_get_calendar_service_passes_stored_credential(self):
        provider = AppleProvider()
        stored = _apple_stored()
        svc = provider.get_calendar_service("conn-1", stored)
        assert svc._stored is stored


# --------------------------------------------------------------------------- #
# CalDAVCalendarService server_url validation                                  #
# --------------------------------------------------------------------------- #


def _caldav_stored(server_url: str | None = None) -> StoredCredential:
    config = {"server_url": server_url} if server_url is not None else None
    return StoredCredential(
        provider_key="caldav",
        auth_kind=AuthKind.BASIC,
        credentials=BasicCredentials(username="u", password="p"),
        provider_config=config,
    )


class TestCalDAVServerUrlValidation:
    def test_missing_server_url_raises(self):
        with pytest.raises(InvalidCredentialFormatError, match="server_url"):
            CalDAVCalendarService("conn-1", _caldav_stored())

    def test_empty_server_url_raises(self):
        with pytest.raises(InvalidCredentialFormatError, match="server_url"):
            CalDAVCalendarService("conn-1", _caldav_stored(server_url=""))

    def test_valid_server_url_accepted(self):
        svc = CalDAVCalendarService(
            "conn-1", _caldav_stored(server_url="https://caldav.example.com")
        )
        assert svc._server_url == "https://caldav.example.com"

    def test_trailing_slash_stripped(self):
        svc = CalDAVCalendarService(
            "conn-1", _caldav_stored(server_url="https://caldav.example.com/")
        )
        assert not svc._server_url.endswith("/")

    def test_apple_subclass_does_not_require_server_url(self):
        """AppleCalendarService hardcodes iCloud URL; no server_url in provider_config needed."""
        svc = AppleCalendarService("conn-1", _apple_stored())
        assert svc._server_url == ICLOUD_CALDAV_URL
