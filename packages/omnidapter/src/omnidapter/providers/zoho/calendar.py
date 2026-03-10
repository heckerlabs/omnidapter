"""
Zoho Calendar service implementation.
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
    EventStatus,
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

ZOHO_API_BASE = "https://calendar.zoho.com/api/v1"

_ZOHO_CAPABILITIES = frozenset({
    CalendarCapability.LIST_CALENDARS,
    CalendarCapability.CREATE_EVENT,
    CalendarCapability.UPDATE_EVENT,
    CalendarCapability.DELETE_EVENT,
    CalendarCapability.GET_EVENT,
    CalendarCapability.LIST_EVENTS,
    CalendarCapability.ATTENDEES,
})


def _parse_zoho_datetime(dt_str: str | None) -> datetime | None:
    if not dt_str:
        return None
    try:
        # Zoho format: "yyyyMMdd'T'HHmmssZ"
        return datetime.strptime(dt_str, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except Exception:
            return None


def _normalize_zoho_event(raw: dict, calendar_id: str) -> CalendarEvent:
    start = _parse_zoho_datetime(raw.get("dateandtime", {}).get("start")) or datetime.now(tz=timezone.utc)
    end = _parse_zoho_datetime(raw.get("dateandtime", {}).get("end")) or datetime.now(tz=timezone.utc)

    attendees = []
    for att in raw.get("attendees", []):
        attendees.append(Attendee(
            email=att.get("email", ""),
            display_name=att.get("name"),
            status=AttendeeStatus.NEEDS_ACTION,
        ))

    return CalendarEvent(
        event_id=raw.get("uid", raw.get("id", "")),
        calendar_id=calendar_id,
        summary=raw.get("title"),
        description=raw.get("description"),
        location=raw.get("location"),
        status=EventStatus.CONFIRMED,
        start=start,
        end=end,
        all_day=raw.get("isallday", False),
        attendees=attendees,
        provider_data={k: v for k, v in raw.items()
                       if k not in ("uid", "id", "title", "description", "location",
                                    "dateandtime", "attendees", "isallday")},
    )


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

    def _auth_headers(self) -> dict[str, str]:
        creds = self._stored.credentials
        if isinstance(creds, OAuth2Credentials):
            return {"Authorization": f"Zoho-oauthtoken {creds.access_token}"}
        return {}

    async def list_calendars(self) -> list[Calendar]:
        self._require_capability(CalendarCapability.LIST_CALENDARS)
        response = await self._http.request(
            "GET", f"{ZOHO_API_BASE}/calendars", headers=self._auth_headers()
        )
        data = response.json()
        calendars = []
        for cal in data.get("calendars", []):
            calendars.append(Calendar(
                calendar_id=cal.get("uid", cal.get("id", "")),
                summary=cal.get("name", ""),
                description=cal.get("description"),
                timezone=cal.get("timezone"),
                is_primary=cal.get("isprimary", False),
                provider_data=cal,
            ))
        return calendars

    async def get_availability(self, request: GetAvailabilityRequest) -> AvailabilityResponse:
        self._require_capability(CalendarCapability.LIST_EVENTS)
        return AvailabilityResponse(
            queried_calendars=request.calendar_ids,
            time_min=request.time_min,
            time_max=request.time_max,
            busy_intervals=[],
        )

    async def create_event(self, request: CreateEventRequest) -> CalendarEvent:
        self._require_capability(CalendarCapability.CREATE_EVENT)
        import json as _json

        def _fmt(dt):
            if isinstance(dt, datetime):
                return dt.strftime("%Y%m%dT%H%M%SZ")
            return dt.strftime("%Y%m%d")

        body = {
            "title": request.summary,
            "dateandtime": {"start": _fmt(request.start), "end": _fmt(request.end)},
            "isallday": request.all_day,
        }
        if request.description:
            body["description"] = request.description
        if request.location:
            body["location"] = request.location
        if request.attendees:
            body["attendees"] = [{"email": a.email, "name": a.display_name or a.email}
                                  for a in request.attendees]

        response = await self._http.request(
            "POST",
            f"{ZOHO_API_BASE}/calendars/{request.calendar_id}/events",
            headers=self._auth_headers(),
            json={"eventdata": _json.dumps(body)},
        )
        data = response.json()
        events = data.get("events", [])
        raw = events[0] if events else body
        return _normalize_zoho_event(raw, request.calendar_id)

    async def update_event(self, request: UpdateEventRequest) -> CalendarEvent:
        self._require_capability(CalendarCapability.UPDATE_EVENT)
        import json as _json

        def _fmt(dt):
            if isinstance(dt, datetime):
                return dt.strftime("%Y%m%dT%H%M%SZ")
            return dt.strftime("%Y%m%d")

        body: dict[str, Any] = {}
        if request.summary is not None:
            body["title"] = request.summary
        if request.description is not None:
            body["description"] = request.description
        if request.location is not None:
            body["location"] = request.location
        if request.start is not None and request.end is not None:
            body["dateandtime"] = {
                "start": _fmt(request.start),
                "end": _fmt(request.end),
            }

        response = await self._http.request(
            "PUT",
            f"{ZOHO_API_BASE}/calendars/{request.calendar_id}/events/{request.event_id}",
            headers=self._auth_headers(),
            json={"eventdata": _json.dumps(body)},
        )
        data = response.json()
        events = data.get("events", [])
        raw = events[0] if events else body
        return _normalize_zoho_event(raw, request.calendar_id)

    async def delete_event(self, calendar_id: str, event_id: str) -> None:
        self._require_capability(CalendarCapability.DELETE_EVENT)
        await self._http.request(
            "DELETE",
            f"{ZOHO_API_BASE}/calendars/{calendar_id}/events/{event_id}",
            headers=self._auth_headers(),
        )

    async def get_event(self, calendar_id: str, event_id: str) -> CalendarEvent:
        self._require_capability(CalendarCapability.GET_EVENT)
        response = await self._http.request(
            "GET",
            f"{ZOHO_API_BASE}/calendars/{calendar_id}/events/{event_id}",
            headers=self._auth_headers(),
        )
        data = response.json()
        events = data.get("events", [{}])
        return _normalize_zoho_event(events[0] if events else {}, calendar_id)

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
        params: dict[str, Any] = {}
        if time_min:
            params["startdatetime"] = time_min.strftime("%Y%m%dT%H%M%SZ") if hasattr(time_min, "strftime") else time_min
        if time_max:
            params["enddatetime"] = time_max.strftime("%Y%m%dT%H%M%SZ") if hasattr(time_max, "strftime") else time_max
        if page_token:
            params["start"] = page_token
        if extra:
            params.update(extra)

        response = await self._http.request(
            "GET",
            f"{ZOHO_API_BASE}/calendars/{calendar_id}/events",
            headers=self._auth_headers(),
            params=params,
        )
        data = response.json()
        events = [_normalize_zoho_event(e, calendar_id) for e in data.get("events", [])]
        return Page(items=events, next_page_token=None)
