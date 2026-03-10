"""
Google Calendar service implementation.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from omnidapter.auth.models import OAuth2Credentials
from omnidapter.core.errors import UnsupportedCapabilityError
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


def _parse_event_time(time_obj: dict) -> datetime | date:
    """Parse a Google event time object into datetime or date."""
    if "dateTime" in time_obj:
        dt = datetime.fromisoformat(time_obj["dateTime"].replace("Z", "+00:00"))
        return dt
    elif "date" in time_obj:
        return date.fromisoformat(time_obj["date"])
    raise ValueError(f"Unrecognized time format: {time_obj}")


def _format_event_time(dt: datetime | date, all_day: bool) -> dict:
    """Format a datetime/date into a Google event time object."""
    if all_day or isinstance(dt, date) and not isinstance(dt, datetime):
        return {"date": dt.isoformat() if isinstance(dt, date) else dt.date().isoformat()}
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return {"dateTime": dt.isoformat()}
    return {"date": str(dt)}


def _normalize_attendee_status(status: str) -> AttendeeStatus:
    mapping = {
        "accepted": AttendeeStatus.ACCEPTED,
        "declined": AttendeeStatus.DECLINED,
        "tentative": AttendeeStatus.TENTATIVE,
        "needsAction": AttendeeStatus.NEEDS_ACTION,
    }
    return mapping.get(status, AttendeeStatus.UNKNOWN)


def _normalize_event(raw: dict, calendar_id: str) -> CalendarEvent:
    """Normalize a raw Google Calendar event dict into CalendarEvent."""
    start_obj = raw.get("start", {})
    end_obj = raw.get("end", {})
    start = _parse_event_time(start_obj)
    end = _parse_event_time(end_obj)
    all_day = "date" in start_obj

    organizer_raw = raw.get("organizer")
    organizer = None
    if organizer_raw:
        organizer = Organizer(
            email=organizer_raw.get("email", ""),
            display_name=organizer_raw.get("displayName"),
            is_self=organizer_raw.get("self", False),
        )

    attendees = []
    for att in raw.get("attendees", []):
        attendees.append(Attendee(
            email=att.get("email", ""),
            display_name=att.get("displayName"),
            status=_normalize_attendee_status(att.get("responseStatus", "needsAction")),
            is_organizer=att.get("organizer", False),
            is_self=att.get("self", False),
            is_resource=att.get("resource", False),
            optional=att.get("optional", False),
            comment=att.get("comment"),
        ))

    recurrence = None
    recurrence_rules = raw.get("recurrence", [])
    recurring_event_id = raw.get("recurringEventId")
    if recurrence_rules or recurring_event_id:
        original_start = None
        orig_start_raw = raw.get("originalStartTime")
        if orig_start_raw:
            try:
                original_start = _parse_event_time(orig_start_raw)
            except Exception:
                pass
        recurrence = Recurrence(
            rules=recurrence_rules,
            recurring_event_id=recurring_event_id,
            original_start_time=original_start,
        )

    conference_data = None
    conf_raw = raw.get("conferenceData")
    if conf_raw:
        entry_points = []
        for ep in conf_raw.get("entryPoints", []):
            entry_points.append(ConferenceEntryPoint(
                entry_point_type=ep.get("entryPointType", "video"),
                uri=ep.get("uri", ""),
                label=ep.get("label"),
                pin=ep.get("pin"),
            ))
        cs = conf_raw.get("conferenceSolution", {})
        conference_data = ConferenceData(
            conference_id=conf_raw.get("conferenceId"),
            conference_solution_name=cs.get("name"),
            entry_points=entry_points,
            join_url=next(
                (ep.uri for ep in entry_points if ep.entry_point_type == "video"),
                None,
            ),
        )

    status_map = {
        "confirmed": EventStatus.CONFIRMED,
        "tentative": EventStatus.TENTATIVE,
        "cancelled": EventStatus.CANCELLED,
    }
    visibility_map = {
        "public": EventVisibility.PUBLIC,
        "private": EventVisibility.PRIVATE,
        "confidential": EventVisibility.CONFIDENTIAL,
        "default": EventVisibility.DEFAULT,
    }

    created_at = None
    if raw.get("created"):
        try:
            created_at = datetime.fromisoformat(raw["created"].replace("Z", "+00:00"))
        except Exception:
            pass

    updated_at = None
    if raw.get("updated"):
        try:
            updated_at = datetime.fromisoformat(raw["updated"].replace("Z", "+00:00"))
        except Exception:
            pass

    return CalendarEvent(
        event_id=raw["id"],
        calendar_id=calendar_id,
        summary=raw.get("summary"),
        description=raw.get("description"),
        location=raw.get("location"),
        status=status_map.get(raw.get("status", "confirmed"), EventStatus.CONFIRMED),
        visibility=visibility_map.get(raw.get("visibility", "default"), EventVisibility.DEFAULT),
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
        html_link=raw.get("htmlLink"),
        ical_uid=raw.get("iCalUID"),
        etag=raw.get("etag"),
        sequence=raw.get("sequence"),
        provider_data={
            k: v for k, v in raw.items()
            if k not in (
                "id", "summary", "description", "location", "status", "visibility",
                "start", "end", "organizer", "attendees", "recurrence",
                "recurringEventId", "originalStartTime", "conferenceData",
                "created", "updated", "htmlLink", "iCalUID", "etag", "sequence",
            )
        },
    )


def _normalize_calendar(raw: dict) -> Calendar:
    """Normalize a raw Google CalendarListEntry into Calendar."""
    return Calendar(
        calendar_id=raw["id"],
        summary=raw.get("summary", ""),
        description=raw.get("description"),
        timezone=raw.get("timeZone"),
        is_primary=raw.get("primary", False),
        is_read_only=raw.get("accessRole", "") in ("reader", "freeBusyReader"),
        background_color=raw.get("backgroundColor"),
        foreground_color=raw.get("foregroundColor"),
        provider_data={k: v for k, v in raw.items()
                       if k not in ("id", "summary", "description", "timeZone",
                                    "primary", "accessRole", "backgroundColor", "foregroundColor")},
    )


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
                all_calendars.append(_normalize_calendar(item))
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
        body = self._build_event_body(request)
        url = f"{GOOGLE_API_BASE}/calendars/{request.calendar_id}/events"
        params = {}
        if request.conference_data:
            params["conferenceDataVersion"] = "1"
        response = await self._http.request(
            "POST", url, headers=self._auth_headers(), json=body, params=params or None
        )
        return _normalize_event(response.json(), request.calendar_id)

    async def update_event(self, request: UpdateEventRequest) -> CalendarEvent:
        self._require_capability(CalendarCapability.UPDATE_EVENT)
        body = {}
        if request.summary is not None:
            body["summary"] = request.summary
        if request.description is not None:
            body["description"] = request.description
        if request.location is not None:
            body["location"] = request.location
        if request.start is not None:
            body["start"] = _format_event_time(request.start, request.all_day or False)
        if request.end is not None:
            body["end"] = _format_event_time(request.end, request.all_day or False)
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
        return _normalize_event(response.json(), request.calendar_id)

    async def delete_event(self, calendar_id: str, event_id: str) -> None:
        self._require_capability(CalendarCapability.DELETE_EVENT)
        url = f"{GOOGLE_API_BASE}/calendars/{calendar_id}/events/{event_id}"
        await self._http.request("DELETE", url, headers=self._auth_headers())

    async def get_event(self, calendar_id: str, event_id: str) -> CalendarEvent:
        self._require_capability(CalendarCapability.GET_EVENT)
        url = f"{GOOGLE_API_BASE}/calendars/{calendar_id}/events/{event_id}"
        response = await self._http.request("GET", url, headers=self._auth_headers())
        return _normalize_event(response.json(), calendar_id)

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
        events = [_normalize_event(item, calendar_id) for item in data.get("items", [])]
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

    def _build_event_body(self, request: CreateEventRequest) -> dict:
        body: dict[str, Any] = {
            "summary": request.summary,
            "start": _format_event_time(request.start, request.all_day),
            "end": _format_event_time(request.end, request.all_day),
        }
        if request.timezone:
            if "timeZone" not in body.get("start", {}):
                body["start"]["timeZone"] = request.timezone
            if "timeZone" not in body.get("end", {}):
                body["end"]["timeZone"] = request.timezone
        if request.description:
            body["description"] = request.description
        if request.location:
            body["location"] = request.location
        if request.status:
            body["status"] = request.status
        if request.visibility:
            body["visibility"] = request.visibility
        if request.attendees:
            body["attendees"] = [
                {"email": a.email, "displayName": a.display_name, "optional": a.optional}
                for a in request.attendees
            ]
        if request.recurrence:
            body["recurrence"] = request.recurrence.rules
        body.update(request.extra)
        return body
