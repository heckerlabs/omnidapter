"""
Shared fixtures and utilities for integration tests.

Integration tests require real provider credentials supplied via environment
variables. They are marked with `@pytest.mark.integration` and skipped by default.
Run them using:

    uv run poe test-integration-core

Each provider also needs its own env vars; see the individual test modules
for the full list.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

import pytest
from omnidapter.auth.models import BasicCredentials, OAuth2Credentials
from omnidapter.core.errors import ProviderAPIError, TokenRefreshError
from omnidapter.core.metadata import AuthKind
from omnidapter.stores.credentials import StoredCredential

# Prefix added to every test-created event summary so tests can filter their
# own events and avoid touching unrelated calendar data.
EVENT_PREFIX = "[omnidapter-test]"

# Default page size used in pagination tests.  Tests create PAGE_SIZE + 2
# events so that at least two pages are required.
PAGINATION_PAGE_SIZE = 5

# Shared attendee emails used by integration tests that create invited events.
# Override to mailboxes you control to avoid delivery-failure noise.
INTEGRATION_ATTENDEE_EMAIL_ENV = "OMNIDAPTER_TEST_ATTENDEE_EMAIL"
DEFAULT_INTEGRATION_ATTENDEE_EMAIL = "integration-attendee@example.com"


# --------------------------------------------------------------------------- #
# Shared utilities                                                             #
# --------------------------------------------------------------------------- #


@pytest.fixture
def retry_read():
    """
    Return an async helper that retries a callable up to *max_attempts* times
    with *delay* seconds between attempts.

    Useful after write operations that may have propagation delays.

    Usage::

        fetched = await retry_read(lambda: svc.get_event(cal_id, event_id))
    """

    async def _retry(coro_fn, *, max_attempts: int = 3, delay: float = 1.0):
        last_exc: Exception | None = None
        for attempt in range(max_attempts):
            try:
                return await coro_fn()
            except Exception as exc:
                last_exc = exc
                if attempt < max_attempts - 1:
                    await asyncio.sleep(delay)
        assert last_exc is not None
        raise last_exc

    return _retry


# --------------------------------------------------------------------------- #
# Credential helpers                                                           #
# --------------------------------------------------------------------------- #


def _require_env(*var_names: str) -> None:
    """Skip the test/fixture if any of the listed env vars are absent."""
    missing = [v for v in var_names if not os.getenv(v)]
    if missing:
        pytest.skip(f"Missing env vars: {', '.join(missing)}")


def _stale_oauth2_stored(provider_key: str, refresh_token: str) -> StoredCredential:
    """Build a StoredCredential with a deliberately expired access token.

    Used to exercise the token-refresh path end-to-end.
    """
    return StoredCredential(
        provider_key=provider_key,
        auth_kind=AuthKind.OAUTH2,
        credentials=OAuth2Credentials(
            access_token="stale-will-be-refreshed",
            refresh_token=refresh_token,
            expires_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
        ),
    )


@pytest.fixture(scope="session")
def integration_attendee_emails() -> list[str]:
    """Return attendee emails from env (comma-separated) with a safe default."""
    raw = os.getenv(INTEGRATION_ATTENDEE_EMAIL_ENV, DEFAULT_INTEGRATION_ATTENDEE_EMAIL)
    emails: list[str] = []
    for part in raw.split(","):
        email = part.strip()
        if email and email not in emails:
            emails.append(email)
    return emails or [DEFAULT_INTEGRATION_ATTENDEE_EMAIL]


@pytest.fixture(scope="session")
def integration_attendee_email(integration_attendee_emails: list[str]) -> str:
    """Backward-compatible single attendee fixture (first configured email)."""
    return integration_attendee_emails[0]


# --------------------------------------------------------------------------- #
# Google fixtures                                                              #
# --------------------------------------------------------------------------- #

_GOOGLE_VARS = (
    "OMNIDAPTER_TEST_GOOGLE_CLIENT_ID",
    "OMNIDAPTER_TEST_GOOGLE_CLIENT_SECRET",
    "OMNIDAPTER_TEST_GOOGLE_REFRESH_TOKEN",
)


@pytest.fixture(scope="module")
async def google_stored():
    """Fresh Google OAuth2 credentials obtained by exchanging the test refresh token."""
    _require_env(*_GOOGLE_VARS)
    from omnidapter.providers.google.provider import GoogleProvider

    stale = _stale_oauth2_stored("google", os.environ["OMNIDAPTER_TEST_GOOGLE_REFRESH_TOKEN"])
    provider = GoogleProvider(
        client_id=os.environ["OMNIDAPTER_TEST_GOOGLE_CLIENT_ID"],
        client_secret=os.environ["OMNIDAPTER_TEST_GOOGLE_CLIENT_SECRET"],
    )
    try:
        return await provider.refresh_token(stale)
    except (TokenRefreshError, ProviderAPIError) as exc:
        pytest.skip(f"Google integration credentials unusable: {exc}")


@pytest.fixture(scope="module")
def google_provider():
    _require_env(*_GOOGLE_VARS)
    from omnidapter.providers.google.provider import GoogleProvider

    return GoogleProvider(
        client_id=os.environ["OMNIDAPTER_TEST_GOOGLE_CLIENT_ID"],
        client_secret=os.environ["OMNIDAPTER_TEST_GOOGLE_CLIENT_SECRET"],
    )


@pytest.fixture(scope="module")
def google_service(google_provider, google_stored):
    return google_provider.get_calendar_service("integration-google", google_stored)


@pytest.fixture(scope="module")
async def google_calendar_id(google_service):
    """Return the calendar ID to use for tests: env var override or first calendar."""
    cal_id = os.getenv("OMNIDAPTER_TEST_GOOGLE_CALENDAR_ID")
    if cal_id:
        return cal_id
    calendars = await google_service.list_calendars()
    assert calendars, "No Google calendars found on this account"
    return calendars[0].calendar_id


# --------------------------------------------------------------------------- #
# Microsoft fixtures                                                           #
# --------------------------------------------------------------------------- #

_MICROSOFT_VARS = (
    "OMNIDAPTER_TEST_MICROSOFT_CLIENT_ID",
    "OMNIDAPTER_TEST_MICROSOFT_CLIENT_SECRET",
    "OMNIDAPTER_TEST_MICROSOFT_REFRESH_TOKEN",
)


@pytest.fixture(scope="module")
async def microsoft_stored():
    _require_env(*_MICROSOFT_VARS)
    from omnidapter.providers.microsoft.provider import MicrosoftProvider

    stale = _stale_oauth2_stored("microsoft", os.environ["OMNIDAPTER_TEST_MICROSOFT_REFRESH_TOKEN"])
    provider = MicrosoftProvider(
        client_id=os.environ["OMNIDAPTER_TEST_MICROSOFT_CLIENT_ID"],
        client_secret=os.environ["OMNIDAPTER_TEST_MICROSOFT_CLIENT_SECRET"],
    )
    try:
        return await provider.refresh_token(stale)
    except (TokenRefreshError, ProviderAPIError) as exc:
        pytest.skip(f"Microsoft integration credentials unusable: {exc}")


@pytest.fixture(scope="module")
def microsoft_provider():
    _require_env(*_MICROSOFT_VARS)
    from omnidapter.providers.microsoft.provider import MicrosoftProvider

    return MicrosoftProvider(
        client_id=os.environ["OMNIDAPTER_TEST_MICROSOFT_CLIENT_ID"],
        client_secret=os.environ["OMNIDAPTER_TEST_MICROSOFT_CLIENT_SECRET"],
    )


@pytest.fixture(scope="module")
def microsoft_service(microsoft_provider, microsoft_stored):
    return microsoft_provider.get_calendar_service("integration-microsoft", microsoft_stored)


@pytest.fixture(scope="module")
async def microsoft_calendar_id(microsoft_service):
    cal_id = os.getenv("OMNIDAPTER_TEST_MICROSOFT_CALENDAR_ID")
    if cal_id:
        return cal_id
    calendars = await microsoft_service.list_calendars()
    assert calendars, "No Microsoft calendars found on this account"
    return calendars[0].calendar_id


# --------------------------------------------------------------------------- #
# Zoho fixtures                                                                #
# --------------------------------------------------------------------------- #

_ZOHO_VARS = (
    "OMNIDAPTER_TEST_ZOHO_CLIENT_ID",
    "OMNIDAPTER_TEST_ZOHO_CLIENT_SECRET",
    "OMNIDAPTER_TEST_ZOHO_REFRESH_TOKEN",
)


@pytest.fixture(scope="module")
async def zoho_stored():
    _require_env(*_ZOHO_VARS)
    from omnidapter.providers.zoho.provider import ZohoProvider

    stale = _stale_oauth2_stored("zoho", os.environ["OMNIDAPTER_TEST_ZOHO_REFRESH_TOKEN"])
    provider = ZohoProvider(
        client_id=os.environ["OMNIDAPTER_TEST_ZOHO_CLIENT_ID"],
        client_secret=os.environ["OMNIDAPTER_TEST_ZOHO_CLIENT_SECRET"],
    )
    try:
        return await provider.refresh_token(stale)
    except (TokenRefreshError, ProviderAPIError) as exc:
        pytest.skip(f"Zoho integration credentials unusable: {exc}")


@pytest.fixture(scope="module")
def zoho_provider():
    _require_env(*_ZOHO_VARS)
    from omnidapter.providers.zoho.provider import ZohoProvider

    return ZohoProvider(
        client_id=os.environ["OMNIDAPTER_TEST_ZOHO_CLIENT_ID"],
        client_secret=os.environ["OMNIDAPTER_TEST_ZOHO_CLIENT_SECRET"],
    )


@pytest.fixture(scope="module")
def zoho_service(zoho_provider, zoho_stored):
    return zoho_provider.get_calendar_service("integration-zoho", zoho_stored)


@pytest.fixture(scope="module")
async def zoho_calendar_id(zoho_service):
    cal_id = os.getenv("OMNIDAPTER_TEST_ZOHO_CALENDAR_ID")
    if cal_id:
        return cal_id
    calendars = await zoho_service.list_calendars()
    assert calendars, "No Zoho calendars found on this account"
    return calendars[0].calendar_id


# --------------------------------------------------------------------------- #
# CalDAV fixtures                                                              #
# --------------------------------------------------------------------------- #

_CALDAV_VARS = (
    "OMNIDAPTER_TEST_CALDAV_URL",
    "OMNIDAPTER_TEST_CALDAV_USERNAME",
    "OMNIDAPTER_TEST_CALDAV_PASSWORD",
)


@pytest.fixture(scope="module")
def caldav_stored():
    _require_env(*_CALDAV_VARS)
    return StoredCredential(
        provider_key="caldav",
        auth_kind=AuthKind.BASIC,
        credentials=BasicCredentials(
            username=os.environ["OMNIDAPTER_TEST_CALDAV_USERNAME"],
            password=os.environ["OMNIDAPTER_TEST_CALDAV_PASSWORD"],
        ),
        provider_config={"server_url": os.environ["OMNIDAPTER_TEST_CALDAV_URL"]},
    )


@pytest.fixture(scope="module")
def caldav_service(caldav_stored):
    from omnidapter.providers.caldav.provider import CalDAVProvider

    return CalDAVProvider().get_calendar_service("integration-caldav", caldav_stored)


@pytest.fixture(scope="module")
async def caldav_calendar_id(caldav_service):
    cal_id = os.getenv("OMNIDAPTER_TEST_CALDAV_CALENDAR_ID")
    if cal_id:
        return cal_id
    calendars = await caldav_service.list_calendars()
    assert calendars, "No CalDAV calendars found at the configured server URL"
    return calendars[0].calendar_id


# --------------------------------------------------------------------------- #
# Apple Calendar fixtures                                                      #
# --------------------------------------------------------------------------- #

_APPLE_VARS = (
    "OMNIDAPTER_TEST_APPLE_USERNAME",
    "OMNIDAPTER_TEST_APPLE_PASSWORD",
)


@pytest.fixture(scope="module")
def apple_stored():
    _require_env(*_APPLE_VARS)
    return StoredCredential(
        provider_key="apple",
        auth_kind=AuthKind.BASIC,
        credentials=BasicCredentials(
            username=os.environ["OMNIDAPTER_TEST_APPLE_USERNAME"],
            password=os.environ["OMNIDAPTER_TEST_APPLE_PASSWORD"],
        ),
    )


@pytest.fixture(scope="module")
def apple_service(apple_stored):
    from omnidapter.providers.apple.provider import AppleProvider

    return AppleProvider().get_calendar_service("integration-apple", apple_stored)


@pytest.fixture(scope="module")
async def apple_calendar_id(apple_service):
    cal_id = os.getenv("OMNIDAPTER_TEST_APPLE_CALENDAR_ID")
    if cal_id:
        return cal_id
    calendars = await apple_service.list_calendars()
    assert calendars, "No Apple calendars found on this iCloud account"
    return calendars[0].calendar_id
