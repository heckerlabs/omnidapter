from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from omnidapter.auth.kinds import AuthKind
from omnidapter.auth.models import BasicCredentials, OAuth2Credentials
from omnidapter.core.errors import ConnectionNotFoundError, RateLimitError
from omnidapter.core.omnidapter import Omnidapter
from omnidapter.services.calendar.models import EventTime, EventUpsertRequest
from omnidapter.stores.credentials import StoredCredential
from omnidapter.transport.client import TransportClient, TransportResponse


class MemoryCredentialStore:
    def __init__(self):
        self.data = {}

    async def get_credentials(self, connection_id: str):
        return self.data.get(connection_id)

    async def save_credentials(self, connection_id: str, credentials: StoredCredential):
        self.data[connection_id] = credentials

    async def delete_credentials(self, connection_id: str):
        self.data.pop(connection_id, None)


class MemoryOAuthStateStore:
    def __init__(self):
        self.data = {}

    async def save_state(self, state_id, payload, expires_at):
        self.data[state_id] = payload

    async def load_state(self, state_id):
        return self.data.get(state_id)

    async def delete_state(self, state_id):
        self.data.pop(state_id, None)


@pytest.mark.asyncio
async def test_connection_not_found_fails_fast():
    omni = Omnidapter(MemoryCredentialStore(), MemoryOAuthStateStore())
    with pytest.raises(ConnectionNotFoundError):
        await omni.connection("missing")


@pytest.mark.asyncio
async def test_oauth_complete_persists_credentials_and_callback():
    credentials = MemoryCredentialStore()
    states = MemoryOAuthStateStore()
    touched = []

    async def callback(connection_id, cred):
        touched.append((connection_id, cred.provider_key))

    omni = Omnidapter(credentials, states, on_credentials_updated=callback)
    begin = await omni.oauth.begin("google", "conn-1", "https://app/callback")
    stored = await omni.oauth.complete("google", "conn-1", "abc", begin.state, "https://app/callback")
    assert stored.provider_key == "google"
    assert credentials.data["conn-1"].credentials.access_token.startswith("token-")
    assert touched == [("conn-1", "google")]


@pytest.mark.asyncio
async def test_auto_refresh_occurs_before_call_and_under_lock():
    credentials = MemoryCredentialStore()
    states = MemoryOAuthStateStore()
    expired = StoredCredential(
        provider_key="google",
        auth_kind=AuthKind.OAUTH2,
        credentials=OAuth2Credentials(
            access_token="old",
            refresh_token="r1",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        ),
    )
    await credentials.save_credentials("conn-1", expired)
    omni = Omnidapter(credentials, states)
    conn = await omni.connection("conn-1")
    cal = conn.calendar()

    async def run_once():
        return await cal.list_calendars()

    await asyncio.gather(run_once(), run_once())
    refreshed = credentials.data["conn-1"].credentials
    assert isinstance(refreshed, OAuth2Credentials)
    assert refreshed.access_token == "refreshed-token"


@pytest.mark.asyncio
async def test_async_iterator_pagination_lists_all_items():
    credentials = MemoryCredentialStore()
    states = MemoryOAuthStateStore()
    await credentials.save_credentials(
        "conn-1",
        StoredCredential(provider_key="google", auth_kind=AuthKind.BASIC, credentials=BasicCredentials(username="u", password="p")),
    )
    omni = Omnidapter(credentials, states)
    conn = await omni.connection("conn-1")
    cal = conn.calendar()

    now = datetime.now(timezone.utc)
    for i in range(5):
        await cal.create_event(
            EventUpsertRequest(
                calendar_id="primary",
                summary=f"e{i}",
                start=EventTime(date_time=now),
                end=EventTime(date_time=now),
            )
        )
    seen = []
    async for evt in cal.list_events("primary"):
        seen.append(evt.id)
    assert len(seen) == 5


@pytest.mark.asyncio
async def test_rate_limit_context_exposed():
    async def sender(method, url, headers, body):
        return TransportResponse(
            429,
            body="too many",
            headers={"Retry-After": "5", "X-RateLimit-Remaining": "0", "X-Request-Id": "req-1"},
        )

    client = TransportClient("google", sender)
    with pytest.raises(RateLimitError) as exc:
        await client.request("GET", "https://example")
    assert exc.value.retry_after == 5.0
    assert exc.value.provider_request_id == "req-1"


def test_provider_metadata_exposes_requirements():
    omni = Omnidapter(MemoryCredentialStore(), MemoryOAuthStateStore())
    meta = omni.describe_provider("caldav")
    assert "server_url" in meta.config_requirements
    assert meta.oauth.supported is False
