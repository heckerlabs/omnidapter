"""
Microsoft Calendar (Graph API) service implementation.
"""
from __future__ import annotations

from typing import Any

from omnidapter.auth.models import OAuth2Credentials
from omnidapter.providers.microsoft import mappers
from omnidapter.services.calendar.capabilities import CalendarCapability
from omnidapter.services.calendar.interface import CalendarService
from omnidapter.services.calendar.models import (
    AvailabilityResponse,
    Calendar,
    CalendarEvent,
    EventStatus,
    EventVisibility,
    FreeBusyInterval,
)
from omnidapter.services.calendar.pagination import Page
from omnidapter.services.calendar.requests import (
    CreateEventRequest,
    GetAvailabilityRequest,
    UpdateEventRequest,
)
from omnidapter.stores.credentials import StoredCredential
from omnidapter.transport.client import OmnidapterHttpClient
from omnidapter.transport.retry import RetryPolicy

MS_GRAPH_BASE = "https://graph.microsoft.com/v1.0"

_MS_CAPABILITIES = frozenset({
    CalendarCapability.LIST_CALENDARS,
    CalendarCapability.GET_AVAILABILITY,
    CalendarCapability.CREATE_EVENT,
    CalendarCapability.UPDATE_EVENT,
    CalendarCapability.DELETE_EVENT,
    CalendarCapability.GET_EVENT,
    CalendarCapability.LIST_EVENTS,
    CalendarCapability.CONFERENCE_LINKS,
    CalendarCapability.RECURRENCE,
    CalendarCapability.ATTENDEES,
})


class MicrosoftCalendarService(CalendarService):
    """Microsoft Graph API calendar implementation."""

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
            provider_key="microsoft",
            retry_policy=retry_policy,
            hooks=hooks,
        )

    @property
    def capabilities(self) -> frozenset[CalendarCapability]:
        return _MS_CAPABILITIES

    @property
    def _provider_key(self) -> str:
        return "microsoft"

    def _auth_headers(self) -> dict[str, str]:
        creds = self._stored.credentials
        if isinstance(creds, OAuth2Credentials):
            return {
                "Authorization": f"Bearer {creds.access_token}",
                "Content-Type": "application/json",
            }
        return {}

    async def list_calendars(self) -> list[Calendar]:
        self._require_capability(CalendarCapability.LIST_CALENDARS)
        url = f"{MS_GRAPH_BASE}/me/calendars"
        all_calendars = []
        while url:
            response = await self._http.request("GET", url, headers=self._auth_headers())
            data = response.json()
            for item in data.get("value", []):
                all_calendars.append(mappers.to_calendar(item))
            url = data.get("@odata.nextLink")
        return all_calendars

    async def get_availability(self, request: GetAvailabilityRequest) -> AvailabilityResponse:
        self._require_capability(CalendarCapability.GET_AVAILABILITY)
        url = f"{MS_GRAPH_BASE}/me/calendar/getSchedule"
        body = {
            "schedules": request.calendar_ids,
            "startTime": {"dateTime": request.time_min.isoformat(), "timeZone": "UTC"},
            "endTime": {"dateTime": request.time_max.isoformat(), "timeZone": "UTC"},
            "availabilityViewInterval": 30,
        }
        response = await self._http.request("POST", url, headers=self._auth_headers(), json=body)
        data = response.json()

        busy_intervals = []
        for schedule in data.get("value", []):
            for item in schedule.get("scheduleItems", []):
                if item.get("status", "").lower() in ("busy", "tentative", "oof"):
                    start = mappers._parse_ms_datetime(item.get("start", {}))
                    end = mappers._parse_ms_datetime(item.get("end", {}))
                    if start and end:
                        busy_intervals.append(FreeBusyInterval(start=start, end=end))

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

        url = f"{MS_GRAPH_BASE}/me/calendars/{request.calendar_id}/events"
        response = await self._http.request("POST", url, headers=self._auth_headers(), json=body)
        return mappers.to_calendar_event(response.json(), request.calendar_id)

    async def update_event(self, request: UpdateEventRequest) -> CalendarEvent:
        self._require_capability(CalendarCapability.UPDATE_EVENT)
        url = f"{MS_GRAPH_BASE}/me/calendars/{request.calendar_id}/events/{request.event_id}"
        body: dict[str, Any] = {}
        if request.summary is not None:
            body["subject"] = request.summary
        if request.description is not None:
            body["body"] = {"contentType": "text", "content": request.description}
        if request.location is not None:
            body["location"] = {"displayName": request.location}
        if request.start is not None:
            body["start"] = mappers._format_ms_datetime(request.start, request.timezone)
        if request.end is not None:
            body["end"] = mappers._format_ms_datetime(request.end, request.timezone)
        if request.attendees is not None:
            body["attendees"] = [
                {"emailAddress": {"address": a.email, "name": a.display_name or ""},
                 "type": "required"}
                for a in request.attendees
            ]
        body.update(request.extra)
        response = await self._http.request("PATCH", url, headers=self._auth_headers(), json=body)
        return mappers.to_calendar_event(response.json(), request.calendar_id)

    async def delete_event(self, calendar_id: str, event_id: str) -> None:
        self._require_capability(CalendarCapability.DELETE_EVENT)
        url = f"{MS_GRAPH_BASE}/me/calendars/{calendar_id}/events/{event_id}"
        await self._http.request("DELETE", url, headers=self._auth_headers())

    async def get_event(self, calendar_id: str, event_id: str) -> CalendarEvent:
        self._require_capability(CalendarCapability.GET_EVENT)
        url = f"{MS_GRAPH_BASE}/me/calendars/{calendar_id}/events/{event_id}"
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
        if page_token:
            url = page_token
            params = None
        else:
            url = f"{MS_GRAPH_BASE}/me/calendars/{calendar_id}/events"
            params: dict[str, Any] = {"$orderby": "start/dateTime"}
            if time_min:
                ts = time_min.isoformat() if hasattr(time_min, "isoformat") else time_min
                params["$filter"] = f"start/dateTime ge '{ts}'"
            if page_size:
                params["$top"] = str(page_size)
            if extra:
                params.update(extra)

        response = await self._http.request(
            "GET", url, headers=self._auth_headers(), params=params
        )
        data = response.json()
        events = [mappers.to_calendar_event(item, calendar_id) for item in data.get("value", [])]
        return Page(items=events, next_page_token=data.get("@odata.nextLink"))


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
