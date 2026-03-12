"""
Zoho Calendar service implementation.
"""

from __future__ import annotations

import json as _json
from datetime import date, datetime, timezone
from typing import Any

from omnidapter.auth.models import OAuth2Credentials
from omnidapter.core.errors import ProviderAPIError, TransportError
from omnidapter.providers.zoho import mappers
from omnidapter.services.calendar.capabilities import CalendarCapability
from omnidapter.services.calendar.interface import CalendarService
from omnidapter.services.calendar.models import (
    AvailabilityResponse,
    Calendar,
    CalendarEvent,
    EventStatus,
)
from omnidapter.services.calendar.requests import (
    CreateEventRequest,
    GetAvailabilityRequest,
    UpdateEventRequest,
)
from omnidapter.stores.credentials import StoredCredential
from omnidapter.transport.client import OmnidapterHttpClient
from omnidapter.transport.retry import RetryPolicy

ZOHO_API_BASE = "https://calendar.zoho.com/api/v1"

_ZOHO_CAPABILITIES = frozenset(
    {
        CalendarCapability.LIST_CALENDARS,
        CalendarCapability.CREATE_EVENT,
        CalendarCapability.UPDATE_EVENT,
        CalendarCapability.DELETE_EVENT,
        CalendarCapability.GET_EVENT,
        CalendarCapability.LIST_EVENTS,
        CalendarCapability.ATTENDEES,
    }
)


def _as_utc_datetime(value: datetime | date) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)


def _in_time_window(
    event: CalendarEvent,
    *,
    time_min: datetime | date | None,
    time_max: datetime | date | None,
) -> bool:
    event_start = _as_utc_datetime(event.start)
    event_end = _as_utc_datetime(event.end)

    if time_min is not None and event_end <= _as_utc_datetime(time_min):
        return False
    return not (time_max is not None and event_start >= _as_utc_datetime(time_max))


class ZohoCalendarService(CalendarService):
    """Zoho Calendar API implementation."""

    def __init__(
        self,
        connection_id: str,
        stored_credential: StoredCredential,
        retry_policy: RetryPolicy | None = None,
        hooks: Any = None,
    ) -> None:
        self._connection_id = connection_id
        self._stored = stored_credential
        self._http = OmnidapterHttpClient(
            provider_key="zoho",
            retry_policy=retry_policy,
            hooks=hooks,
        )

    @property
    def capabilities(self) -> frozenset[CalendarCapability]:
        return _ZOHO_CAPABILITIES

    @property
    def _provider_key(self) -> str:
        return "zoho"

    async def _resolve_stored_credential(self) -> StoredCredential:
        resolver = getattr(self, "_credential_resolver", None)
        if resolver is None:
            return self._stored

        latest = await resolver(self._connection_id)
        self._stored = latest
        return latest

    async def _auth_headers(self) -> dict[str, str]:
        creds = (await self._resolve_stored_credential()).credentials
        if isinstance(creds, OAuth2Credentials):
            return {"Authorization": f"Zoho-oauthtoken {creds.access_token}"}
        return {}

    async def _headers_with_event_etag(self, calendar_id: str, event_id: str) -> dict[str, str]:
        headers = await self._auth_headers()
        try:
            event = await self.get_event(calendar_id, event_id)
        except (ProviderAPIError, TransportError):
            return headers
        etag = (event.provider_data or {}).get("etag")
        if etag:
            headers = dict(headers)
            headers["ETag"] = str(etag)
        return headers

    async def list_calendars(self) -> list[Calendar]:
        self._require_capability(CalendarCapability.LIST_CALENDARS)
        response = await self._http.request(
            "GET", f"{ZOHO_API_BASE}/calendars", headers=await self._auth_headers()
        )
        data = response.json()
        return [mappers.to_calendar(cal) for cal in data.get("calendars", [])]

    async def get_availability(self, request: GetAvailabilityRequest) -> AvailabilityResponse:
        self._require_capability(CalendarCapability.GET_AVAILABILITY)
        return AvailabilityResponse(
            queried_calendars=request.calendar_ids,
            time_min=request.time_min,
            time_max=request.time_max,
            busy_intervals=[],
        )

    async def create_event(self, request: CreateEventRequest) -> CalendarEvent:
        self._require_capability(CalendarCapability.CREATE_EVENT)
        if request.status is not None and request.status != EventStatus.CONFIRMED:
            raise ValueError("Zoho only supports confirmed event status.")
        event = CalendarEvent(
            event_id="",
            calendar_id=request.calendar_id,
            summary=request.summary,
            start=request.start,
            end=request.end,
            all_day=request.all_day,
            description=request.description,
            location=request.location,
            attendees=request.attendees,
        )
        body = mappers.from_calendar_event(event)
        body.update(request.extra)

        response = await self._http.request(
            "POST",
            f"{ZOHO_API_BASE}/calendars/{request.calendar_id}/events",
            headers=await self._auth_headers(),
            params={"eventdata": _json.dumps(body)},
        )
        data = response.json()
        events = data.get("events", [])
        raw = events[0] if events else body
        return mappers.to_calendar_event(raw, request.calendar_id)

    async def update_event(self, request: UpdateEventRequest) -> CalendarEvent:
        self._require_capability(CalendarCapability.UPDATE_EVENT)
        if request.status is not None and request.status != EventStatus.CONFIRMED:
            raise ValueError("Zoho only supports confirmed event status.")
        current = await self.get_event(request.calendar_id, request.event_id)
        body: dict[str, Any] = {}
        if request.summary is not None:
            body["title"] = request.summary
        if request.description is not None:
            body["description"] = request.description
        if request.location is not None:
            body["location"] = request.location

        current_etag = (current.provider_data or {}).get("etag")
        start_value = request.start if request.start is not None else current.start
        end_value = request.end if request.end is not None else current.end
        body["dateandtime"] = {
            "start": mappers._format_zoho_datetime(start_value),
            "end": mappers._format_zoho_datetime(end_value),
        }

        headers = await self._auth_headers()
        if current_etag:
            headers = dict(headers)
            headers["ETag"] = str(current_etag)

        response = await self._http.request(
            "PUT",
            f"{ZOHO_API_BASE}/calendars/{request.calendar_id}/events/{request.event_id}",
            headers=headers,
            params={"eventdata": _json.dumps(body)},
        )
        data = response.json()
        events = data.get("events", [])
        raw = events[0] if events else body
        return mappers.to_calendar_event(raw, request.calendar_id)

    async def delete_event(self, calendar_id: str, event_id: str) -> None:
        self._require_capability(CalendarCapability.DELETE_EVENT)
        await self._http.request(
            "DELETE",
            f"{ZOHO_API_BASE}/calendars/{calendar_id}/events/{event_id}",
            headers=await self._headers_with_event_etag(calendar_id, event_id),
        )

    async def get_event(self, calendar_id: str, event_id: str) -> CalendarEvent:
        self._require_capability(CalendarCapability.GET_EVENT)
        response = await self._http.request(
            "GET",
            f"{ZOHO_API_BASE}/calendars/{calendar_id}/events/{event_id}",
            headers=await self._auth_headers(),
        )
        data = response.json()
        events = data.get("events", [{}])
        return mappers.to_calendar_event(events[0] if events else {}, calendar_id)

    async def list_events(
        self,
        calendar_id: str,
        *,
        time_min=None,
        time_max=None,
        page_size: int | None = None,
        extra: dict | None = None,
    ):
        self._require_capability(CalendarCapability.LIST_EVENTS)
        params: dict[str, Any] = {}
        if isinstance(time_min, (datetime, date)):
            params["start"] = mappers._format_zoho_datetime(time_min)
        elif time_min is not None:
            params["start"] = str(time_min)

        if isinstance(time_max, (datetime, date)):
            params["end"] = mappers._format_zoho_datetime(time_max)
        elif time_max is not None:
            params["end"] = str(time_max)

        if extra:
            params.update(extra)

        window_time_min = time_min if isinstance(time_min, (datetime, date)) else None
        window_time_max = time_max if isinstance(time_max, (datetime, date)) else None
        apply_window_filter = window_time_min is not None or window_time_max is not None

        response = await self._http.request(
            "GET",
            f"{ZOHO_API_BASE}/calendars/{calendar_id}/events",
            headers=await self._auth_headers(),
            params=params,
        )
        data = response.json()
        for e in data.get("events", []):
            event = mappers.to_calendar_event(e, calendar_id)
            if not apply_window_filter or _in_time_window(
                event,
                time_min=window_time_min,
                time_max=window_time_max,
            ):
                yield event
