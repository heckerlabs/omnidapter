"""
Microsoft Calendar (Graph API) service implementation.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from omnidapter.auth.models import OAuth2Credentials
from omnidapter.services.calendar.capabilities import CalendarCapability
from omnidapter.services.calendar.interface import CalendarService
from omnidapter.services.calendar.models import (
    Attendee,
    AttendeeStatus,
    AvailabilityResponse,
    Calendar,
    CalendarEvent,
    ConferenceData,
    ConferenceEntryPoint,
    EventStatus,
    EventVisibility,
    FreeBusyInterval,
    Organizer,
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

_STATUS_MAP = {
    "normal": EventStatus.CONFIRMED,
    "tentative": EventStatus.TENTATIVE,
    "cancelled": EventStatus.CANCELLED,
}

_ATTENDEE_STATUS_MAP = {
    "accepted": AttendeeStatus.ACCEPTED,
    "declined": AttendeeStatus.DECLINED,
    "tentative": AttendeeStatus.TENTATIVE,
    "none": AttendeeStatus.NEEDS_ACTION,
    "notResponded": AttendeeStatus.NEEDS_ACTION,
}


def _parse_ms_datetime(obj: dict | None) -> datetime | date | None:
    if not obj:
        return None
    dt_str = obj.get("dateTime")
    tz_str = obj.get("timeZone", "UTC")
    if not dt_str:
        return None
    # Microsoft uses a format like "2024-01-15T09:00:00.0000000"
    dt_str = dt_str.split(".")[0]  # strip fractional seconds
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _normalize_ms_event(raw: dict, calendar_id: str) -> CalendarEvent:
    start_obj = raw.get("start", {})
    end_obj = raw.get("end", {})
    start = _parse_ms_datetime(start_obj) or datetime.now(tz=timezone.utc)
    end = _parse_ms_datetime(end_obj) or datetime.now(tz=timezone.utc)
    all_day = raw.get("isAllDay", False)

    organizer_raw = raw.get("organizer", {}).get("emailAddress", {})
    organizer = None
    if organizer_raw:
        organizer = Organizer(
            email=organizer_raw.get("address", ""),
            display_name=organizer_raw.get("name"),
        )

    attendees = []
    for att in raw.get("attendees", []):
        email_obj = att.get("emailAddress", {})
        status_obj = att.get("status", {})
        attendees.append(Attendee(
            email=email_obj.get("address", ""),
            display_name=email_obj.get("name"),
            status=_ATTENDEE_STATUS_MAP.get(
                status_obj.get("response", "none"), AttendeeStatus.NEEDS_ACTION
            ),
        ))

    recurrence = None
    if raw.get("recurrence"):
        recurrence = Recurrence(
            provider_data=raw["recurrence"],
        )

    online_meeting = raw.get("onlineMeeting")
    conference_data = None
    if online_meeting and online_meeting.get("joinUrl"):
        conference_data = ConferenceData(
            join_url=online_meeting["joinUrl"],
            entry_points=[ConferenceEntryPoint(
                entry_point_type="video",
                uri=online_meeting["joinUrl"],
            )],
            provider_data=online_meeting,
        )

    created_at = None
    if raw.get("createdDateTime"):
        try:
            created_at = datetime.fromisoformat(
                raw["createdDateTime"].replace("Z", "+00:00")
            )
        except Exception:
            pass

    updated_at = None
    if raw.get("lastModifiedDateTime"):
        try:
            updated_at = datetime.fromisoformat(
                raw["lastModifiedDateTime"].replace("Z", "+00:00")
            )
        except Exception:
            pass

    return CalendarEvent(
        event_id=raw["id"],
        calendar_id=calendar_id,
        summary=raw.get("subject"),
        description=raw.get("body", {}).get("content") if raw.get("body") else None,
        location=raw.get("location", {}).get("displayName") if raw.get("location") else None,
        status=_STATUS_MAP.get(raw.get("showAs", "normal"), EventStatus.CONFIRMED),
        visibility=EventVisibility.DEFAULT,
        start=start,
        end=end,
        all_day=all_day,
        timezone=start_obj.get("timeZone"),
        organizer=organizer,
        attendees=attendees,
        recurrence=recurrence,
        conference_data=conference_data,
        created_at=created_at,
        updated_at=updated_at,
        html_link=raw.get("webLink"),
        ical_uid=raw.get("iCalUId"),
        etag=raw.get("@odata.etag"),
        provider_data={k: v for k, v in raw.items()
                       if k not in ("id", "subject", "body", "location", "showAs",
                                    "start", "end", "isAllDay", "organizer", "attendees",
                                    "recurrence", "onlineMeeting", "createdDateTime",
                                    "lastModifiedDateTime", "webLink", "iCalUId")},
    )


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
                all_calendars.append(Calendar(
                    calendar_id=item["id"],
                    summary=item.get("name", ""),
                    description=item.get("description"),
                    timezone=item.get("timeZone"),
                    is_primary=item.get("isDefaultCalendar", False),
                    is_read_only=not item.get("canEdit", True),
                    background_color=item.get("hexColor"),
                    provider_data={k: v for k, v in item.items()
                                   if k not in ("id", "name", "description", "timeZone",
                                                "isDefaultCalendar", "canEdit", "hexColor")},
                ))
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
                    start_obj = item.get("start", {})
                    end_obj = item.get("end", {})
                    start = _parse_ms_datetime(start_obj)
                    end = _parse_ms_datetime(end_obj)
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
        url = f"{MS_GRAPH_BASE}/me/calendars/{request.calendar_id}/events"
        body = self._build_event_body(request)
        response = await self._http.request("POST", url, headers=self._auth_headers(), json=body)
        return _normalize_ms_event(response.json(), request.calendar_id)

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
            body["start"] = self._format_ms_time(request.start, request.timezone)
        if request.end is not None:
            body["end"] = self._format_ms_time(request.end, request.timezone)
        if request.attendees is not None:
            body["attendees"] = [
                {"emailAddress": {"address": a.email, "name": a.display_name or ""},
                 "type": "required"}
                for a in request.attendees
            ]
        body.update(request.extra)
        response = await self._http.request("PATCH", url, headers=self._auth_headers(), json=body)
        return _normalize_ms_event(response.json(), request.calendar_id)

    async def delete_event(self, calendar_id: str, event_id: str) -> None:
        self._require_capability(CalendarCapability.DELETE_EVENT)
        url = f"{MS_GRAPH_BASE}/me/calendars/{calendar_id}/events/{event_id}"
        await self._http.request("DELETE", url, headers=self._auth_headers())

    async def get_event(self, calendar_id: str, event_id: str) -> CalendarEvent:
        self._require_capability(CalendarCapability.GET_EVENT)
        url = f"{MS_GRAPH_BASE}/me/calendars/{calendar_id}/events/{event_id}"
        response = await self._http.request("GET", url, headers=self._auth_headers())
        return _normalize_ms_event(response.json(), calendar_id)

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
            # Microsoft uses full URL as skip token
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
        events = [_normalize_ms_event(item, calendar_id) for item in data.get("value", [])]
        return Page(items=events, next_page_token=data.get("@odata.nextLink"))

    def _format_ms_time(self, dt: datetime | date, tz: str | None) -> dict:
        if isinstance(dt, datetime):
            return {"dateTime": dt.isoformat(), "timeZone": tz or "UTC"}
        return {"dateTime": f"{dt}T00:00:00", "timeZone": tz or "UTC"}

    def _build_event_body(self, request: CreateEventRequest) -> dict[str, Any]:
        body: dict[str, Any] = {
            "subject": request.summary,
            "start": self._format_ms_time(request.start, request.timezone),
            "end": self._format_ms_time(request.end, request.timezone),
            "isAllDay": request.all_day,
        }
        if request.description:
            body["body"] = {"contentType": "text", "content": request.description}
        if request.location:
            body["location"] = {"displayName": request.location}
        if request.attendees:
            body["attendees"] = [
                {"emailAddress": {"address": a.email, "name": a.display_name or ""},
                 "type": "required"}
                for a in request.attendees
            ]
        body.update(request.extra)
        return body
