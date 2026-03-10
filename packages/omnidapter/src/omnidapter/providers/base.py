from __future__ import annotations

from datetime import datetime, timedelta, timezone

from omnidapter.auth.models import OAuth2Credentials, OAuthTokenResult
from omnidapter.core.errors import UnsupportedCapabilityError
from omnidapter.services.calendar.models import AvailabilityResponse, Calendar, Event, EventTime, EventUpsertRequest
from omnidapter.services.calendar.pagination import PaginatedResult
from omnidapter.stores.credentials import StoredCredential


class SimpleOAuthAdapter:
    def __init__(self, provider_key: str) -> None:
        self.provider_key = provider_key

    async def build_authorization_url(self, connection_id: str, state: str, redirect_uri: str, code_verifier: str) -> str:
        return f"https://auth.{self.provider_key}.example/authorize?state={state}&redirect_uri={redirect_uri}"

    async def exchange_code(self, code: str, redirect_uri: str, code_verifier: str) -> OAuthTokenResult:
        return OAuthTokenResult(
            credentials=OAuth2Credentials(
                access_token=f"token-{code}",
                refresh_token="refresh-token",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                scope=["calendar.read", "calendar.write"],
            ),
            granted_scopes=["calendar.read", "calendar.write"],
            provider_account_id="acct_123",
        )

    async def refresh(self, credential: StoredCredential) -> StoredCredential:
        creds = credential.credentials
        if not isinstance(creds, OAuth2Credentials):
            return credential
        creds.access_token = "refreshed-token"
        creds.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        credential.credentials = creds
        return credential


class UnsupportedCalendarService:
    async def list_calendars(self) -> list[Calendar]:
        raise UnsupportedCapabilityError("list_calendars unsupported")

    async def get_availability(self, calendar_id: str) -> AvailabilityResponse:
        raise UnsupportedCapabilityError("get_availability unsupported")

    async def create_event(self, payload: EventUpsertRequest) -> Event:
        raise UnsupportedCapabilityError("create_event unsupported")

    async def update_event(self, event_id: str, payload: EventUpsertRequest) -> Event:
        raise UnsupportedCapabilityError("update_event unsupported")

    async def delete_event(self, event_id: str) -> None:
        raise UnsupportedCapabilityError("delete_event unsupported")

    async def get_event(self, event_id: str) -> Event:
        raise UnsupportedCapabilityError("get_event unsupported")

    async def list_events_page(self, calendar_id: str, page_token: str | None = None) -> PaginatedResult[Event]:
        raise UnsupportedCapabilityError("list_events unsupported")


class InMemoryCalendarService:
    def __init__(self, provider_key: str):
        self.provider_key = provider_key
        self._events: dict[str, Event] = {}

    async def list_calendars(self) -> list[Calendar]:
        return [Calendar(id="primary", summary=f"{self.provider_key} Primary")]

    async def get_availability(self, calendar_id: str) -> AvailabilityResponse:
        return AvailabilityResponse(calendar_id=calendar_id, busy=[])

    async def create_event(self, payload: EventUpsertRequest) -> Event:
        event = Event(
            id=f"evt_{len(self._events) + 1}",
            calendar_id=payload.calendar_id,
            summary=payload.summary,
            start=payload.start,
            end=payload.end,
        )
        self._events[event.id] = event
        return event

    async def update_event(self, event_id: str, payload: EventUpsertRequest) -> Event:
        event = self._events[event_id]
        event.summary = payload.summary
        return event

    async def delete_event(self, event_id: str) -> None:
        self._events.pop(event_id, None)

    async def get_event(self, event_id: str) -> Event:
        return self._events[event_id]

    async def list_events_page(self, calendar_id: str, page_token: str | None = None) -> PaginatedResult[Event]:
        ordered = list(self._events.values())
        start = int(page_token) if page_token else 0
        chunk = ordered[start : start + 2]
        next_token = str(start + 2) if start + 2 < len(ordered) else None
        return PaginatedResult[Event](items=chunk, next_page_token=next_token)

    async def list_events(self, calendar_id: str):
        page = await self.list_events_page(calendar_id)
        while True:
            for item in page.items:
                yield item
            if not page.next_page_token:
                break
            page = await self.list_events_page(calendar_id, page.next_page_token)


def default_event_time() -> EventTime:
    return EventTime(date_time=datetime.now(timezone.utc))
