"""
CalDAV calendar service implementation.

Uses raw HTTP with CalDAV/WebDAV PROPFIND, REPORT, PUT, DELETE methods.
"""

from __future__ import annotations

import secrets
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urlparse

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
from omnidapter.services.calendar.requests import (
    CreateCalendarRequest,
    CreateEventRequest,
    GetAvailabilityRequest,
    UpdateCalendarRequest,
    UpdateEventRequest,
)
from omnidapter.stores.credentials import StoredCredential
from omnidapter.transport.client import OmnidapterHttpClient
from omnidapter.transport.retry import RetryPolicy

_CALDAV_CAPABILITIES = frozenset(
    {
        CalendarCapability.LIST_CALENDARS,
        CalendarCapability.GET_CALENDAR,
        CalendarCapability.CREATE_CALENDAR,
        CalendarCapability.UPDATE_CALENDAR,
        CalendarCapability.DELETE_CALENDAR,
        CalendarCapability.CREATE_EVENT,
        CalendarCapability.UPDATE_EVENT,
        CalendarCapability.DELETE_EVENT,
        CalendarCapability.GET_EVENT,
        CalendarCapability.LIST_EVENTS,
        CalendarCapability.RECURRENCE,
        CalendarCapability.ATTENDEES,
    }
)

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
        *,
        _server_url: str | None = None,
    ) -> None:
        self._connection_id = connection_id
        self._stored = stored_credential
        config = stored_credential.provider_config or {}
        server_url = (_server_url or config.get("server_url", "")).rstrip("/")
        if not server_url:
            from omnidapter.core.errors import InvalidCredentialFormatError

            raise InvalidCredentialFormatError(
                "CalDAV credentials missing required 'server_url' in provider_config. "
                "Set provider_config={'server_url': 'https://caldav.example.com/user/calendars/'}.",
                provider_key="caldav",
            )
        self._server_url = server_url
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

    def _resolve_calendar_url(self, calendar_id: str) -> str:
        cid = (calendar_id or "").strip()
        if cid.startswith("http://") or cid.startswith("https://"):
            return cid.rstrip("/")
        if cid.startswith("/"):
            parsed_base = urlparse(self._server_url)
            return f"{parsed_base.scheme}://{parsed_base.netloc}{cid}".rstrip("/")
        return f"{self._server_url}/{cid.strip('/')}"

    async def _propfind(self, url: str, body: str, *, depth: str) -> ET.Element:
        headers = {**self._auth_headers(), "Depth": depth}
        response = await self._http.request(
            "PROPFIND",
            url,
            headers=headers,
            data=body.encode(),
        )
        return ET.fromstring(response.text)

    async def _discover_icloud_calendar_home_url(self) -> str:
        principal_body = """<?xml version="1.0" encoding="UTF-8"?>
<D:propfind xmlns:D="DAV:">
  <D:prop>
    <D:current-user-principal/>
  </D:prop>
</D:propfind>"""
        principal_root = await self._propfind(self._server_url + "/", principal_body, depth="0")
        principal_href = principal_root.findtext(".//{DAV:}current-user-principal/{DAV:}href", "")
        if not principal_href:
            from omnidapter.core.errors import ProviderAPIError
            from omnidapter.transport.correlation import new_correlation_id

            raise ProviderAPIError(
                "Failed to discover iCloud current-user-principal",
                provider_key=self._provider_key,
                correlation_id=new_correlation_id(),
            )

        if principal_href.startswith("http://") or principal_href.startswith("https://"):
            principal_url = principal_href.rstrip("/") + "/"
        else:
            principal_url = f"{self._server_url}/{principal_href.strip('/')}"
            principal_url = principal_url.rstrip("/") + "/"

        home_set_body = """<?xml version="1.0" encoding="UTF-8"?>
<D:propfind xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop>
    <C:calendar-home-set/>
  </D:prop>
</D:propfind>"""
        home_root = await self._propfind(principal_url, home_set_body, depth="0")
        home_href = home_root.findtext(
            ".//{urn:ietf:params:xml:ns:caldav}calendar-home-set/{DAV:}href", ""
        )
        if not home_href:
            from omnidapter.core.errors import ProviderAPIError
            from omnidapter.transport.correlation import new_correlation_id

            raise ProviderAPIError(
                "Failed to discover iCloud calendar-home-set",
                provider_key=self._provider_key,
                correlation_id=new_correlation_id(),
            )

        if home_href.startswith("http://") or home_href.startswith("https://"):
            return home_href.rstrip("/") + "/"

        parsed_base = urlparse(self._server_url)
        return f"{parsed_base.scheme}://{parsed_base.netloc}/{home_href.strip('/')}" + "/"

    async def _calendar_home_base_url(self) -> str:
        calendars = await self.list_calendars()
        if calendars:
            first = self._resolve_calendar_url(calendars[0].calendar_id).rstrip("/")
            return first.rsplit("/", 1)[0] + "/"
        base = self._server_url.rstrip("/")
        return base + "/"

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
        discovery_url = self._server_url + "/"
        if self._server_hint.value == "icloud":
            discovery_url = await self._discover_icloud_calendar_home_url()

        headers = {**self._auth_headers(), "Depth": "1"}
        response = await self._http.request(
            "PROPFIND",
            discovery_url,
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

    async def get_calendar(self, calendar_id: str) -> Calendar:
        self._require_capability(CalendarCapability.GET_CALENDAR)
        calendars = await self.list_calendars()
        requested = mappers.parse_collection_href(calendar_id).rstrip("/")
        for calendar in calendars:
            current = mappers.parse_collection_href(calendar.calendar_id).rstrip("/")
            if current == requested:
                return calendar

        from omnidapter.core.errors import ProviderAPIError
        from omnidapter.transport.correlation import new_correlation_id

        raise ProviderAPIError(
            f"Calendar not found: {calendar_id}",
            provider_key=self._provider_key,
            status_code=404,
            correlation_id=new_correlation_id(),
        )

    async def create_calendar(self, request: CreateCalendarRequest) -> Calendar:
        self._require_capability(CalendarCapability.CREATE_CALENDAR)
        slug = mappers.slugify_calendar_name(request.summary)
        base_url = await self._calendar_home_base_url()
        url = f"{base_url}{slug}-{secrets.token_hex(4)}/"
        props = mappers.from_create_calendar_request(request)
        mkcalendar_body = f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<C:mkcalendar xmlns:D=\"DAV:\" xmlns:C=\"urn:ietf:params:xml:ns:caldav\">
  <D:set>
    <D:prop>
      <D:displayname>{props.get("displayname", "")}</D:displayname>
      <C:calendar-description>{props.get("calendar-description", "")}</C:calendar-description>
      <C:calendar-timezone>{props.get("calendar-timezone", "")}</C:calendar-timezone>
    </D:prop>
  </D:set>
</C:mkcalendar>"""
        await self._http.request(
            "MKCALENDAR",
            url,
            headers=self._auth_headers(),
            data=mkcalendar_body.encode(),
        )
        return await self.get_calendar(mappers.parse_collection_href(url))

    async def update_calendar(self, request: UpdateCalendarRequest) -> Calendar:
        self._require_capability(CalendarCapability.UPDATE_CALENDAR)
        calendar_url = self._resolve_calendar_url(request.calendar_id) + "/"
        props = mappers.from_update_calendar_request(request)
        set_lines = []
        if "displayname" in props:
            set_lines.append(f"<D:displayname>{props['displayname']}</D:displayname>")
        if "calendar-description" in props:
            set_lines.append(
                f"<C:calendar-description>{props['calendar-description']}</C:calendar-description>"
            )
        if "calendar-timezone" in props:
            set_lines.append(
                f"<C:calendar-timezone>{props['calendar-timezone']}</C:calendar-timezone>"
            )
        if not set_lines:
            return await self.get_calendar(request.calendar_id)

        proppatch_body = f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<D:propertyupdate xmlns:D=\"DAV:\" xmlns:C=\"urn:ietf:params:xml:ns:caldav\">
  <D:set>
    <D:prop>
      {"".join(set_lines)}
    </D:prop>
  </D:set>
</D:propertyupdate>"""
        await self._http.request(
            "PROPPATCH",
            calendar_url,
            headers=self._auth_headers(),
            data=proppatch_body.encode(),
        )
        return await self.get_calendar(request.calendar_id)

    async def delete_calendar(self, calendar_id: str) -> None:
        self._require_capability(CalendarCapability.DELETE_CALENDAR)
        calendar_url = self._resolve_calendar_url(calendar_id) + "/"
        await self._http.request("DELETE", calendar_url, headers=self._auth_headers())

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
        calendar_url = self._resolve_calendar_url(request.calendar_id)
        url = f"{calendar_url}/{uid}.ics"
        headers = {**self._auth_headers(), "Content-Type": "text/calendar; charset=utf-8"}
        await self._http.request("PUT", url, headers=headers, data=ical.encode())
        return event

    async def update_event(self, request: UpdateEventRequest) -> CalendarEvent:
        self._require_capability(CalendarCapability.UPDATE_EVENT)
        existing = await self.get_event(request.calendar_id, request.event_id)
        updated = existing.model_copy(
            update={
                k: v
                for k, v in {
                    "summary": request.summary,
                    "start": request.start,
                    "end": request.end,
                    "all_day": request.all_day,
                    "description": request.description,
                    "location": request.location,
                    "attendees": request.attendees,
                    "recurrence": request.recurrence,
                }.items()
                if v is not None
            }
        )
        ical = mappers.from_calendar_event(updated)
        calendar_url = self._resolve_calendar_url(request.calendar_id)
        url = f"{calendar_url}/{request.event_id}.ics"
        headers = {**self._auth_headers(), "Content-Type": "text/calendar; charset=utf-8"}
        await self._http.request("PUT", url, headers=headers, data=ical.encode())
        return await self.get_event(request.calendar_id, request.event_id)

    async def delete_event(self, calendar_id: str, event_id: str) -> None:
        self._require_capability(CalendarCapability.DELETE_EVENT)
        calendar_url = self._resolve_calendar_url(calendar_id)
        url = f"{calendar_url}/{event_id}.ics"
        await self._http.request("DELETE", url, headers=self._auth_headers())

    async def get_event(self, calendar_id: str, event_id: str) -> CalendarEvent:
        self._require_capability(CalendarCapability.GET_EVENT)
        calendar_url = self._resolve_calendar_url(calendar_id)
        url = f"{calendar_url}/{event_id}.ics"
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
        time_filter = ""
        if time_min and time_max:
            ts_min = mappers._format_ical_datetime(time_min)
            ts_max = mappers._format_ical_datetime(time_max)
            time_filter = f"""
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

        url = self._resolve_calendar_url(calendar_id) + "/"
        headers = {**self._auth_headers(), "Depth": "1"}
        response = await self._http.request(
            "REPORT", url, headers=headers, data=report_body.encode()
        )

        try:
            root = ET.fromstring(response.text)
            for resp in root.findall(".//{DAV:}response"):
                cal_data = resp.findtext(".//{urn:ietf:params:xml:ns:caldav}calendar-data", "")
                if cal_data:
                    event = mappers.to_calendar_event(cal_data, calendar_id)
                    if event:
                        yield event
        except ET.ParseError:
            pass
