"""
CalDAV calendar service implementation.

Uses raw HTTP with CalDAV/WebDAV PROPFIND, REPORT, PUT, DELETE methods.
"""
from __future__ import annotations

import secrets
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from typing import Any

from omnidapter.auth.models import BasicCredentials
from omnidapter.providers.caldav.auth import basic_auth_header
from omnidapter.providers.caldav.server_hints import CalDAVServerHint, detect_server_hint
from omnidapter.services.calendar.capabilities import CalendarCapability
from omnidapter.services.calendar.interface import CalendarService
from omnidapter.services.calendar.models import (
    Attendee,
    AttendeeStatus,
    AvailabilityResponse,
    Calendar,
    CalendarEvent,
    EventStatus,
    FreeBusyInterval,
    Recurrence,
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


def _format_ical_datetime(dt: datetime | date, all_day: bool = False) -> str:
    """Format a datetime as iCalendar DTSTART/DTEND value."""
    if all_day or isinstance(dt, date) and not isinstance(dt, datetime):
        if isinstance(dt, datetime):
            return dt.strftime("%Y%m%d")
        return dt.strftime("%Y%m%d")
    if isinstance(dt, datetime):
        if dt.tzinfo is not None:
            return dt.strftime("%Y%m%dT%H%M%SZ")
        return dt.strftime("%Y%m%dT%H%M%SZ")
    return str(dt)


def _parse_ical_datetime(value: str) -> datetime | date:
    """Parse an iCalendar datetime string."""
    value = value.strip()
    if "T" in value:
        value = value.rstrip("Z")
        try:
            dt = datetime.strptime(value, "%Y%m%dT%H%M%S")
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return datetime.now(tz=timezone.utc)
    else:
        try:
            return date(int(value[:4]), int(value[4:6]), int(value[6:8]))
        except (ValueError, IndexError):
            return date.today()


def _build_vcalendar(event_uid: str, request: CreateEventRequest) -> str:
    """Build a VCALENDAR iCalendar string for a new event."""
    dtstart = _format_ical_datetime(request.start, request.all_day)
    dtend = _format_ical_datetime(request.end, request.all_day)
    date_type = "DATE" if request.all_day else "DATE-TIME"

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Omnidapter//Omnidapter//EN",
        "BEGIN:VEVENT",
        f"UID:{event_uid}",
        f"DTSTART;VALUE={date_type}:{dtstart}",
        f"DTEND;VALUE={date_type}:{dtend}",
        f"SUMMARY:{request.summary}",
    ]
    if request.description:
        lines.append(f"DESCRIPTION:{request.description}")
    if request.location:
        lines.append(f"LOCATION:{request.location}")
    for att in request.attendees:
        cn = att.display_name or att.email
        lines.append(f"ATTENDEE;CN={cn}:mailto:{att.email}")
    if request.recurrence:
        for rule in request.recurrence.rules:
            lines.append(rule)
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(lines)


def _parse_vevent(ical_text: str, calendar_id: str) -> CalendarEvent | None:
    """Parse a VEVENT from an iCalendar string."""
    lines = ical_text.replace("\r\n ", "").replace("\n ", "").splitlines()
    props: dict[str, str] = {}
    in_vevent = False
    attendees_raw = []
    rrules = []

    for line in lines:
        if line.strip() == "BEGIN:VEVENT":
            in_vevent = True
            continue
        if line.strip() == "END:VEVENT":
            break
        if not in_vevent:
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key_upper = key.split(";")[0].upper()
        if key_upper == "ATTENDEE":
            attendees_raw.append(value)
        elif key_upper.startswith("RRULE") or key_upper.startswith("EXRULE"):
            rrules.append(line)
        else:
            props[key_upper] = value

    uid = props.get("UID", secrets.token_urlsafe(8))
    summary = props.get("SUMMARY", "")
    description = props.get("DESCRIPTION")
    location = props.get("LOCATION")
    status_str = props.get("STATUS", "CONFIRMED").upper()
    status = {
        "CONFIRMED": EventStatus.CONFIRMED,
        "TENTATIVE": EventStatus.TENTATIVE,
        "CANCELLED": EventStatus.CANCELLED,
    }.get(status_str, EventStatus.CONFIRMED)

    dtstart_str = props.get("DTSTART", "")
    dtend_str = props.get("DTEND", "")
    all_day = "T" not in dtstart_str

    try:
        start = _parse_ical_datetime(dtstart_str)
    except Exception:
        start = datetime.now(tz=timezone.utc)
    try:
        end = _parse_ical_datetime(dtend_str)
    except Exception:
        end = datetime.now(tz=timezone.utc)

    attendees = []
    for att_val in attendees_raw:
        # mailto:email@example.com
        email = att_val.replace("mailto:", "").strip()
        attendees.append(Attendee(email=email))

    recurrence = None
    if rrules:
        recurrence = Recurrence(rules=rrules)

    created_str = props.get("CREATED")
    created_at = None
    if created_str:
        try:
            created_at = _parse_ical_datetime(created_str)
            if isinstance(created_at, date) and not isinstance(created_at, datetime):
                created_at = None
        except Exception:
            pass

    updated_str = props.get("LAST-MODIFIED")
    updated_at = None
    if updated_str:
        try:
            updated_at = _parse_ical_datetime(updated_str)
            if isinstance(updated_at, date) and not isinstance(updated_at, datetime):
                updated_at = None
        except Exception:
            pass

    return CalendarEvent(
        event_id=uid,
        calendar_id=calendar_id,
        summary=summary or None,
        description=description,
        location=location,
        status=status,
        start=start,
        end=end,
        all_day=all_day,
        attendees=attendees,
        recurrence=recurrence,
        created_at=created_at,
        updated_at=updated_at,
        ical_uid=uid,
        provider_data={"raw_props": props},
    )


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
                href = resp.findtext("{DAV:}href", "")
                is_calendar = resp.find(
                    ".//{DAV:}resourcetype/{urn:ietf:params:xml:ns:caldav}calendar"
                )
                if is_calendar is None:
                    continue
                display_name = resp.findtext(".//{DAV:}displayname", "") or href.rstrip("/").split("/")[-1]
                description = resp.findtext(".//{urn:ietf:params:xml:ns:caldav}calendar-description")
                calendars.append(Calendar(
                    calendar_id=href,
                    summary=display_name,
                    description=description,
                ))
        except ET.ParseError:
            pass

        return calendars

    async def get_availability(self, request: GetAvailabilityRequest) -> AvailabilityResponse:
        # CalDAV free-busy requires REPORT — basic implementation
        self._require_capability(CalendarCapability.LIST_EVENTS)
        return AvailabilityResponse(
            queried_calendars=request.calendar_ids,
            time_min=request.time_min,
            time_max=request.time_max,
            busy_intervals=[],
        )

    async def create_event(self, request: CreateEventRequest) -> CalendarEvent:
        self._require_capability(CalendarCapability.CREATE_EVENT)
        uid = secrets.token_urlsafe(16)
        ical = _build_vcalendar(uid, request)
        url = f"{self._server_url}/{request.calendar_id.strip('/')}/{uid}.ics"
        headers = {**self._auth_headers(), "Content-Type": "text/calendar; charset=utf-8"}
        await self._http.request("PUT", url, headers=headers, data=ical.encode())
        return CalendarEvent(
            event_id=uid,
            calendar_id=request.calendar_id,
            summary=request.summary,
            description=request.description,
            location=request.location,
            start=request.start,
            end=request.end,
            all_day=request.all_day,
            ical_uid=uid,
        )

    async def update_event(self, request: UpdateEventRequest) -> CalendarEvent:
        self._require_capability(CalendarCapability.UPDATE_EVENT)
        # Fetch existing, merge changes, re-PUT
        existing = await self.get_event(request.calendar_id, request.event_id)
        merged = CreateEventRequest(
            calendar_id=request.calendar_id,
            summary=request.summary if request.summary is not None else existing.summary or "",
            start=request.start if request.start is not None else existing.start,
            end=request.end if request.end is not None else existing.end,
            all_day=request.all_day if request.all_day is not None else existing.all_day,
            description=request.description if request.description is not None else existing.description,
            location=request.location if request.location is not None else existing.location,
            attendees=request.attendees if request.attendees is not None else existing.attendees,
            recurrence=request.recurrence if request.recurrence is not None else existing.recurrence,
        )
        uid = request.event_id
        ical = _build_vcalendar(uid, merged)
        url = f"{self._server_url}/{request.calendar_id.strip('/')}/{uid}.ics"
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
        event = _parse_vevent(response.text, calendar_id)
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
        # Build a REPORT request for calendar-query
        time_filter = ""
        if time_min and time_max:
            ts_min = _format_ical_datetime(time_min)
            ts_max = _format_ical_datetime(time_max)
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
                    event = _parse_vevent(cal_data, calendar_id)
                    if event:
                        events.append(event)
        except ET.ParseError:
            pass

        return Page(items=events, next_page_token=None)
