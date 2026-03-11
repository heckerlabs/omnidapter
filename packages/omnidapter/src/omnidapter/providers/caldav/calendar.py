"""
CalDAV calendar service implementation.

Uses raw HTTP with CalDAV/WebDAV PROPFIND, REPORT, PUT, DELETE methods.
"""
from __future__ import annotations

import secrets
import xml.etree.ElementTree as ET
from typing import Any

from omnidapter.auth.models import BasicCredentials
from omnidapter.providers.caldav import mappers
from omnidapter.providers.caldav.auth import basic_auth_header
from omnidapter.providers.caldav.server_hints import detect_server_hint
from omnidapter.services.calendar.capabilities import CalendarCapability
from omnidapter.services.calendar.interface import CalendarService
from omnidapter.services.calendar.models import (
    AvailabilityResponse,
    Calendar,
    CalendarEvent,
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

_CALDAV_CAPABILITIES = frozenset({
    CalendarCapability.LIST_CALENDARS,
    CalendarCapability.CREATE_EVENT,
    CalendarCapability.UPDATE_EVENT,
    CalendarCapability.DELETE_EVENT,
    CalendarCapability.GET_EVENT,
    CalendarCapability.LIST_EVENTS,
    CalendarCapability.RECURRENCE,
    CalendarCapability.ATTENDEES,
})

# CalDAV/WebDAV namespaces
NS = {
    "D": "DAV:",
    "C": "urn:ietf:params:xml:ns:caldav",
    "CS": "http://calendarserver.org/ns/",
    "ICAL": "http://apple.com/ns/ical/",
}


class CalDAVCalendarService(CalendarService):
    """CalDAV protocol calendar service implementation."""

    def __init__(
        self,
        connection_id: str,
        stored_credential: StoredCredential,
        retry_policy: RetryPolicy | None = None,
        hooks: Any = None,
    ) -> None:
        self._connection_id = connection_id
        self._stored = stored_credential
        config = stored_credential.provider_config or {}
        self._server_url = config.get("server_url", "").rstrip("/")
        self._server_hint = detect_server_hint(self._server_url)
        self._http = OmnidapterHttpClient(
            provider_key="caldav",
            retry_policy=retry_policy,
            hooks=hooks,
        )

    @property
    def capabilities(self) -> frozenset[CalendarCapability]:
        return _CALDAV_CAPABILITIES

    @property
    def _provider_key(self) -> str:
        return "caldav"

    def _auth_headers(self) -> dict[str, str]:
        creds = self._stored.credentials
        if isinstance(creds, BasicCredentials):
            return {
                "Authorization": basic_auth_header(creds),
                "Content-Type": "application/xml; charset=utf-8",
            }
        return {}

    async def list_calendars(self) -> list[Calendar]:
        self._require_capability(CalendarCapability.LIST_CALENDARS)
        propfind_body = """<?xml version="1.0" encoding="UTF-8"?>
<D:propfind xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop>
    <D:displayname/>
    <D:resourcetype/>
    <C:calendar-description/>
    <C:calendar-timezone/>
  </D:prop>
</D:propfind>"""
        headers = {**self._auth_headers(), "Depth": "1"}
        response = await self._http.request(
            "PROPFIND",
            self._server_url + "/",
            headers=headers,
            data=propfind_body.encode(),
        )

        calendars = []
        try:
            root = ET.fromstring(response.text)
            for resp in root.findall(".//{DAV:}response"):
                calendar = mappers.to_calendar(resp)
                if calendar is not None:
                    calendars.append(calendar)
        except ET.ParseError:
            pass

        return calendars

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
        uid = secrets.token_urlsafe(16)
        event = CalendarEvent(
            event_id=uid,
            calendar_id=request.calendar_id,
            summary=request.summary,
            start=request.start,
            end=request.end,
            all_day=request.all_day,
            description=request.description,
            location=request.location,
            attendees=request.attendees,
            recurrence=request.recurrence,
            ical_uid=uid,
        )
        ical = mappers.from_calendar_event(event)
        url = f"{self._server_url}/{request.calendar_id.strip('/')}/{uid}.ics"
        headers = {**self._auth_headers(), "Content-Type": "text/calendar; charset=utf-8"}
        await self._http.request("PUT", url, headers=headers, data=ical.encode())
        return event

    async def update_event(self, request: UpdateEventRequest) -> CalendarEvent:
        self._require_capability(CalendarCapability.UPDATE_EVENT)
        existing = await self.get_event(request.calendar_id, request.event_id)
        updated = existing.model_copy(update={
            k: v for k, v in {
                "summary": request.summary,
                "start": request.start,
                "end": request.end,
                "all_day": request.all_day,
                "description": request.description,
                "location": request.location,
                "attendees": request.attendees,
                "recurrence": request.recurrence,
            }.items() if v is not None
        })
        ical = mappers.from_calendar_event(updated)
        url = f"{self._server_url}/{request.calendar_id.strip('/')}/{request.event_id}.ics"
        headers = {**self._auth_headers(), "Content-Type": "text/calendar; charset=utf-8"}
        await self._http.request("PUT", url, headers=headers, data=ical.encode())
        return await self.get_event(request.calendar_id, request.event_id)

    async def delete_event(self, calendar_id: str, event_id: str) -> None:
        self._require_capability(CalendarCapability.DELETE_EVENT)
        url = f"{self._server_url}/{calendar_id.strip('/')}/{event_id}.ics"
        await self._http.request("DELETE", url, headers=self._auth_headers())

    async def get_event(self, calendar_id: str, event_id: str) -> CalendarEvent:
        self._require_capability(CalendarCapability.GET_EVENT)
        url = f"{self._server_url}/{calendar_id.strip('/')}/{event_id}.ics"
        headers = {**self._auth_headers(), "Content-Type": "text/calendar"}
        response = await self._http.request("GET", url, headers=headers)
        event = mappers.to_calendar_event(response.text, calendar_id)
        if event is None:
            from omnidapter.core.errors import ProviderAPIError
            from omnidapter.transport.correlation import new_correlation_id
            raise ProviderAPIError(
                "Failed to parse CalDAV event",
                provider_key="caldav",
                correlation_id=new_correlation_id(),
            )
        return event

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
        time_filter = ""
        if time_min and time_max:
            ts_min = mappers._format_ical_datetime(time_min)
            ts_max = mappers._format_ical_datetime(time_max)
            time_filter = f"""
            <C:limit>
              <C:nresults>50</C:nresults>
            </C:limit>
            <C:time-range start="{ts_min}" end="{ts_max}"/>"""

        report_body = f"""<?xml version="1.0" encoding="UTF-8"?>
<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop>
    <D:getetag/>
    <C:calendar-data/>
  </D:prop>
  <C:filter>
    <C:comp-filter name="VCALENDAR">
      <C:comp-filter name="VEVENT">{time_filter}
      </C:comp-filter>
    </C:comp-filter>
  </C:filter>
</C:calendar-query>"""

        url = f"{self._server_url}/{calendar_id.strip('/')}/"
        headers = {**self._auth_headers(), "Depth": "1"}
        response = await self._http.request(
            "REPORT", url, headers=headers, data=report_body.encode()
        )

        events = []
        try:
            root = ET.fromstring(response.text)
            for resp in root.findall(".//{DAV:}response"):
                cal_data = resp.findtext(
                    ".//{urn:ietf:params:xml:ns:caldav}calendar-data", ""
                )
                if cal_data:
                    event = mappers.to_calendar_event(cal_data, calendar_id)
                    if event:
                        events.append(event)
        except ET.ParseError:
            pass

        return Page(items=events, next_page_token=None)
