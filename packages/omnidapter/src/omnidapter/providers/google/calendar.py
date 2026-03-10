"""
Google Calendar service implementation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from omnidapter.auth.models import OAuth2Credentials
from omnidapter.providers.google import mappers
from omnidapter.services.calendar.capabilities import CalendarCapability
from omnidapter.services.calendar.interface import CalendarService
from omnidapter.services.calendar.models import (
    AvailabilityResponse,
    Calendar,
    CalendarEvent,
    EventStatus,
    EventVisibility,
    FreeBusyInterval,
    WatchSubscription,
)
from omnidapter.services.calendar.pagination import Page
from omnidapter.services.calendar.requests import (
    CreateEventRequest,
    CreateWatchRequest,
    GetAvailabilityRequest,
    UpdateEventRequest,
)
from omnidapter.stores.credentials import StoredCredential
from omnidapter.transport.client import OmnidapterHttpClient
from omnidapter.transport.retry import RetryPolicy

GOOGLE_API_BASE = "https://www.googleapis.com/calendar/v3"
_GOOGLE_CAPABILITIES = frozenset({
    CalendarCapability.LIST_CALENDARS,
    CalendarCapability.GET_AVAILABILITY,
    CalendarCapability.CREATE_EVENT,
    CalendarCapability.UPDATE_EVENT,
    CalendarCapability.DELETE_EVENT,
    CalendarCapability.GET_EVENT,
    CalendarCapability.LIST_EVENTS,
    CalendarCapability.CREATE_WATCH,
    CalendarCapability.PARSE_WEBHOOK,
    CalendarCapability.CONFERENCE_LINKS,
    CalendarCapability.RECURRENCE,
    CalendarCapability.ATTENDEES,
})


class GoogleCalendarService(CalendarService):
    """Google Calendar API v3 implementation."""

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
            provider_key="google",
            retry_policy=retry_policy,
            hooks=hooks,
        )

    @property
    def capabilities(self) -> frozenset[CalendarCapability]:
        return _GOOGLE_CAPABILITIES

    @property
    def _provider_key(self) -> str:
        return "google"

    def _auth_headers(self) -> dict[str, str]:
        creds = self._stored.credentials
        if isinstance(creds, OAuth2Credentials):
            return {"Authorization": f"Bearer {creds.access_token}"}
        return {}

    async def list_calendars(self) -> list[Calendar]:
        self._require_capability(CalendarCapability.LIST_CALENDARS)
        url = f"{GOOGLE_API_BASE}/users/me/calendarList"
        all_calendars = []
        page_token = None
        while True:
            params: dict[str, Any] = {}
            if page_token:
                params["pageToken"] = page_token
            response = await self._http.request(
                "GET", url, headers=self._auth_headers(), params=params
            )
            data = response.json()
            for item in data.get("items", []):
                all_calendars.append(mappers.to_calendar(item))
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        return all_calendars

    async def get_availability(
        self, request: GetAvailabilityRequest
    ) -> AvailabilityResponse:
        self._require_capability(CalendarCapability.GET_AVAILABILITY)
        url = f"{GOOGLE_API_BASE}/freeBusy"
        body = {
            "timeMin": request.time_min.isoformat(),
            "timeMax": request.time_max.isoformat(),
            "items": [{"id": cid} for cid in request.calendar_ids],
        }
        if request.timezone:
            body["timeZone"] = request.timezone

        response = await self._http.request(
            "POST", url, headers=self._auth_headers(), json=body
        )
        data = response.json()

        busy_intervals = []
        for cal_id in request.calendar_ids:
            cal_busy = data.get("calendars", {}).get(cal_id, {})
            for interval in cal_busy.get("busy", []):
                busy_intervals.append(FreeBusyInterval(
                    start=datetime.fromisoformat(interval["start"].replace("Z", "+00:00")),
                    end=datetime.fromisoformat(interval["end"].replace("Z", "+00:00")),
                ))

        return AvailabilityResponse(
            queried_calendars=request.calendar_ids,
            time_min=request.time_min,
            time_max=request.time_max,
            busy_intervals=busy_intervals,
            provider_data=data,
        )

    async def create_event(self, request: CreateEventRequest) -> CalendarEvent:
        self._require_capability(CalendarCapability.CREATE_EVENT)
        event = CalendarEvent(
            event_id="",
            calendar_id=request.calendar_id,
            summary=request.summary,
            start=request.start,
            end=request.end,
            all_day=request.all_day,
            timezone=request.timezone,
            description=request.description,
            location=request.location,
            status=_parse_event_status(request.status),
            visibility=_parse_event_visibility(request.visibility),
            attendees=request.attendees,
            recurrence=request.recurrence,
            conference_data=request.conference_data,
            reminders=request.reminders,
        )
        body = mappers.from_calendar_event(event)
        body.update(request.extra)

        url = f"{GOOGLE_API_BASE}/calendars/{request.calendar_id}/events"
        params = {}
        if request.conference_data:
            params["conferenceDataVersion"] = "1"
        response = await self._http.request(
            "POST", url, headers=self._auth_headers(), json=body, params=params or None
        )
        return mappers.to_calendar_event(response.json(), request.calendar_id)

    async def update_event(self, request: UpdateEventRequest) -> CalendarEvent:
        self._require_capability(CalendarCapability.UPDATE_EVENT)
        body: dict[str, Any] = {}
        if request.summary is not None:
            body["summary"] = request.summary
        if request.description is not None:
            body["description"] = request.description
        if request.location is not None:
            body["location"] = request.location
        if request.start is not None:
            body["start"] = mappers._format_event_time(request.start, request.all_day or False)
        if request.end is not None:
            body["end"] = mappers._format_event_time(request.end, request.all_day or False)
        if request.status is not None:
            body["status"] = request.status
        if request.visibility is not None:
            body["visibility"] = request.visibility
        if request.attendees is not None:
            body["attendees"] = [
                {"email": a.email, "displayName": a.display_name, "optional": a.optional}
                for a in request.attendees
            ]
        if request.recurrence is not None:
            body["recurrence"] = request.recurrence.rules
        body.update(request.extra)

        url = f"{GOOGLE_API_BASE}/calendars/{request.calendar_id}/events/{request.event_id}"
        response = await self._http.request(
            "PATCH", url, headers=self._auth_headers(), json=body
        )
        return mappers.to_calendar_event(response.json(), request.calendar_id)

    async def delete_event(self, calendar_id: str, event_id: str) -> None:
        self._require_capability(CalendarCapability.DELETE_EVENT)
        url = f"{GOOGLE_API_BASE}/calendars/{calendar_id}/events/{event_id}"
        await self._http.request("DELETE", url, headers=self._auth_headers())

    async def get_event(self, calendar_id: str, event_id: str) -> CalendarEvent:
        self._require_capability(CalendarCapability.GET_EVENT)
        url = f"{GOOGLE_API_BASE}/calendars/{calendar_id}/events/{event_id}"
        response = await self._http.request("GET", url, headers=self._auth_headers())
        return mappers.to_calendar_event(response.json(), calendar_id)

    async def list_events_page(
        self,
        calendar_id: str,
        *,
        page_token: str | None = None,
        time_min=None,
        time_max=None,
        page_size: int | None = None,
        extra: dict | None = None,
    ) -> Page[CalendarEvent]:
        self._require_capability(CalendarCapability.LIST_EVENTS)
        url = f"{GOOGLE_API_BASE}/calendars/{calendar_id}/events"
        params: dict[str, Any] = {"singleEvents": "true", "orderBy": "startTime"}
        if page_token:
            params["pageToken"] = page_token
        if time_min:
            params["timeMin"] = time_min.isoformat() if hasattr(time_min, "isoformat") else time_min
        if time_max:
            params["timeMax"] = time_max.isoformat() if hasattr(time_max, "isoformat") else time_max
        if page_size:
            params["maxResults"] = str(page_size)
        if extra:
            params.update(extra)

        response = await self._http.request(
            "GET", url, headers=self._auth_headers(), params=params
        )
        data = response.json()
        events = [mappers.to_calendar_event(item, calendar_id) for item in data.get("items", [])]
        return Page(items=events, next_page_token=data.get("nextPageToken"))

    async def _create_watch(self, request: CreateWatchRequest) -> WatchSubscription:
        import secrets
        url = f"{GOOGLE_API_BASE}/calendars/{request.calendar_id}/events/watch"
        body: dict[str, Any] = {
            "id": secrets.token_urlsafe(16),
            "type": "web_hook",
            "address": request.webhook_url,
        }
        if request.token:
            body["token"] = request.token
        if request.expiration:
            body["expiration"] = int(request.expiration.timestamp() * 1000)
        response = await self._http.request(
            "POST", url, headers=self._auth_headers(), json=body
        )
        data = response.json()
        exp = None
        if data.get("expiration"):
            exp = datetime.fromtimestamp(int(data["expiration"]) / 1000, tz=timezone.utc)
        return WatchSubscription(
            subscription_id=data.get("id", ""),
            resource_id=data.get("resourceId"),
            expiration=exp,
            provider_data=data,
        )

    async def _parse_webhook(self, headers: dict[str, str], body: bytes) -> dict:
        from omnidapter.services.calendar.webhooks import WebhookParseResult
        return WebhookParseResult(
            provider_key="google",
            event_type=headers.get("X-Goog-Resource-State"),
            resource_id=headers.get("X-Goog-Resource-ID"),
            channel_id=headers.get("X-Goog-Channel-ID"),
            raw={"headers": headers},
        ).model_dump()


def _parse_event_status(value: str | None) -> EventStatus:
    if value is None:
        return EventStatus.CONFIRMED
    try:
        return EventStatus(value)
    except ValueError:
        return EventStatus.CONFIRMED


def _parse_event_visibility(value: str | None) -> EventVisibility:
    if value is None:
        return EventVisibility.DEFAULT
    try:
        return EventVisibility(value)
    except ValueError:
        return EventVisibility.DEFAULT
