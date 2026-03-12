"""Unit tests for OAuth calendar auth header refresh behaviour."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from omnidapter.auth.models import OAuth2Credentials
from omnidapter.core.metadata import AuthKind
from omnidapter.providers.microsoft.calendar import MicrosoftCalendarService
from omnidapter.providers.zoho.calendar import ZohoCalendarService
from omnidapter.stores.credentials import StoredCredential


def _stored(provider_key: str, access_token: str) -> StoredCredential:
    return StoredCredential(
        provider_key=provider_key,
        auth_kind=AuthKind.OAUTH2,
        credentials=OAuth2Credentials(access_token=access_token),
    )


@pytest.mark.parametrize(
    ("provider_key", "service_factory", "token_prefix"),
    [
        (
            "microsoft",
            lambda stored: MicrosoftCalendarService("conn-1", stored),
            "Bearer ",
        ),
        (
            "zoho",
            lambda stored: ZohoCalendarService("conn-1", stored),
            "Zoho-oauthtoken ",
        ),
    ],
)
async def test_oauth_services_auth_headers_use_latest_credentials(
    provider_key: str,
    service_factory,
    token_prefix: str,
):
    svc = service_factory(_stored(provider_key, "old-token"))
    refreshed = _stored(provider_key, "new-token")
    resolver = AsyncMock(return_value=refreshed)
    svc._credential_resolver = resolver

    headers = await svc._auth_headers()

    resolver.assert_awaited_once_with("conn-1")
    assert headers["Authorization"] == f"{token_prefix}new-token"
    if provider_key == "microsoft":
        assert headers["Content-Type"] == "application/json"


@pytest.mark.parametrize(
    ("provider_key", "service_factory", "token_prefix"),
    [
        (
            "microsoft",
            lambda stored: MicrosoftCalendarService("conn-1", stored),
            "Bearer ",
        ),
        (
            "zoho",
            lambda stored: ZohoCalendarService("conn-1", stored),
            "Zoho-oauthtoken ",
        ),
    ],
)
async def test_oauth_services_auth_headers_use_stored_credentials_without_resolver(
    provider_key: str,
    service_factory,
    token_prefix: str,
):
    svc = service_factory(_stored(provider_key, "stored-token"))

    headers = await svc._auth_headers()

    assert headers["Authorization"] == f"{token_prefix}stored-token"
