# Calendar API

All calendar operations go through a `CalendarService` retrieved from a `Connection`. The service is always provider-specific under the hood, but the interface is uniform across all providers.

## Getting a calendar service

```python
conn = await omni.connection("conn_123")
cal = conn.calendar()
```

`conn.calendar()` raises `UnsupportedCapabilityError` if the provider doesn't support calendars. All built-in providers do, but if you register custom providers you should check first:

```python
from omnidapter.core.metadata import ServiceKind

if conn.supports(ServiceKind.CALENDAR):
    cal = conn.calendar()
```

---

## Checking capability support

Not every provider supports every operation. Before calling methods that may not be universally supported, check capability first.

```python
from omnidapter.services.calendar.capabilities import CalendarCapability

# Check a single capability
if cal.supports(CalendarCapability.GET_AVAILABILITY):
    availability = await cal.get_availability(request)

# Calling without checking raises UnsupportedCapabilityError
```

Capabilities by provider:

| Capability | Google | Microsoft | Zoho | Apple | CalDAV* |
|---|:---:|:---:|:---:|:---:|:---:|
| `list_calendars` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `list_events` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `get_event` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `create_event` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `update_event` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `delete_event` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `get_availability` | ✓ | ✓ | — | — | — |
| `conference_links` | ✓ | ✓ | — | — | — |
| `recurrence` | ✓ | ✓ | — | ✓ | ✓ |
| `attendees` | ✓ | ✓ | ✓ | ✓ | ✓ |

*CalDAV requires manual registration. See [providers.md](providers.md).

---

## `list_calendars`

Returns all calendars accessible to the connection.

```python
calendars = await cal.list_calendars()

for calendar in calendars:
    print(calendar.calendar_id)     # str — use as calendar_id in other calls
    print(calendar.summary)         # str
    print(calendar.timezone)        # str | None  e.g. "America/New_York"
    print(calendar.is_primary)      # bool
    print(calendar.is_read_only)    # bool
    print(calendar.description)     # str | None
    print(calendar.background_color)  # str | None  e.g. "#4285F4"
```

---

## `list_events`

Returns an async iterator over events. Handles pagination internally.

```python
from datetime import datetime, timezone

async for event in cal.list_events(
    calendar_id="primary",
    time_min=datetime(2026, 3, 1, tzinfo=timezone.utc),
    time_max=datetime(2026, 3, 31, tzinfo=timezone.utc),
    page_size=50,                  # optional, per-page hint
):
    print(event.event_id, event.summary, event.start)
```

All parameters except `calendar_id` are optional.

```python
# All events in a calendar (use with care on busy calendars)
async for event in cal.list_events("primary"):
    ...
```

---

## `get_event`

```python
event = await cal.get_event(calendar_id="primary", event_id="abc123")
```

---

## `create_event`

```python
from omnidapter.services.calendar.requests import CreateEventRequest
from omnidapter.services.calendar.models import Attendee, Recurrence, Reminder, ReminderOverride
from datetime import datetime, timezone

event = await cal.create_event(CreateEventRequest(
    calendar_id="primary",
    summary="Team sync",
    start=datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc),
    end=datetime(2026, 3, 15, 11, 0, tzinfo=timezone.utc),
    description="Weekly catch-up",
    location="Conference Room A",
    timezone="America/New_York",
))
```

### All-day events

```python
from datetime import date

event = await cal.create_event(CreateEventRequest(
    calendar_id="primary",
    summary="Company holiday",
    start=date(2026, 12, 25),
    end=date(2026, 12, 26),
    all_day=True,
))
```

### With attendees

```python
event = await cal.create_event(CreateEventRequest(
    calendar_id="primary",
    summary="Interview: Jane Doe",
    start=datetime(2026, 3, 20, 14, 0, tzinfo=timezone.utc),
    end=datetime(2026, 3, 20, 15, 0, tzinfo=timezone.utc),
    attendees=[
        Attendee(email="jane@example.com", display_name="Jane Doe"),
        Attendee(email="hr@example.com", optional=True),
    ],
))
```

### With recurrence (Google/Microsoft/Apple/CalDAV)

```python
event = await cal.create_event(CreateEventRequest(
    calendar_id="primary",
    summary="Weekly standup",
    start=datetime(2026, 3, 16, 9, 0, tzinfo=timezone.utc),
    end=datetime(2026, 3, 16, 9, 30, tzinfo=timezone.utc),
    recurrence=Recurrence(rules=["RRULE:FREQ=WEEKLY;BYDAY=MO"]),
))
```

### With reminders (Google/Microsoft)

```python
event = await cal.create_event(CreateEventRequest(
    calendar_id="primary",
    summary="Doctor appointment",
    start=datetime(2026, 3, 18, 9, 0, tzinfo=timezone.utc),
    end=datetime(2026, 3, 18, 10, 0, tzinfo=timezone.utc),
    reminders=Reminder(overrides=[
        ReminderOverride(method="email", minutes_before=1440),   # 1 day
        ReminderOverride(method="popup", minutes_before=30),
    ]),
))
```

### Provider-specific fields

Use `extra` to pass fields that Omnidapter doesn't model:

```python
event = await cal.create_event(CreateEventRequest(
    calendar_id="primary",
    summary="Lunch",
    start=..., end=...,
    extra={"guestsCanModify": True},   # Google-specific
))
```

---

## `update_event`

Only fields you provide are changed. Omit a field to leave it unchanged.

```python
from omnidapter.services.calendar.requests import UpdateEventRequest

event = await cal.update_event(UpdateEventRequest(
    calendar_id="primary",
    event_id="abc123",
    summary="Updated title",
    location="Room B",
))
```

---

## `delete_event`

```python
await cal.delete_event(calendar_id="primary", event_id="abc123")
```

Returns `None`. Raises `ProviderAPIError` if the event doesn't exist.

---

## `get_availability`

Returns free/busy intervals. Supported by Google and Microsoft only.

```python
from omnidapter.services.calendar.requests import GetAvailabilityRequest

if cal.supports(CalendarCapability.GET_AVAILABILITY):
    result = await cal.get_availability(GetAvailabilityRequest(
        calendar_ids=["primary", "user@example.com"],
        time_min=datetime(2026, 3, 15, 9, 0, tzinfo=timezone.utc),
        time_max=datetime(2026, 3, 15, 18, 0, tzinfo=timezone.utc),
        timezone="America/New_York",
    ))

    for interval in result.busy_intervals:
        print(f"Busy: {interval.start} → {interval.end}")
```

---

## Return models

### `CalendarEvent`

```python
event.event_id          # str
event.calendar_id       # str
event.summary           # str | None
event.description       # str | None
event.location          # str | None
event.start             # datetime | date
event.end               # datetime | date
event.all_day           # bool
event.timezone          # str | None
event.status            # EventStatus: confirmed | tentative | cancelled | unknown
event.visibility        # EventVisibility: public | private | confidential | default
event.organizer         # Organizer | None
event.attendees         # list[Attendee]
event.recurrence        # Recurrence | None
event.conference_data   # ConferenceData | None
event.reminders         # Reminder | None
event.created_at        # datetime | None
event.updated_at        # datetime | None
event.html_link         # str | None  — browser link to event
event.ical_uid          # str | None  — stable RFC 5545 UID
event.etag              # str | None
event.provider_data     # dict | None — raw provider response, not covered by semver
```

### `Attendee`

```python
attendee.email          # str
attendee.display_name   # str | None
attendee.status         # AttendeeStatus: accepted | declined | tentative | needs_action | unknown
attendee.is_organizer   # bool
attendee.is_self        # bool
attendee.optional       # bool
```

### `ConferenceData` (Google / Microsoft)

```python
conf = event.conference_data
conf.join_url                    # str | None  — main join URL
conf.conference_solution_name    # str | None  — e.g. "Google Meet"
conf.entry_points                # list[ConferenceEntryPoint]
conf.entry_points[0].uri         # str
conf.entry_points[0].entry_point_type  # "video" | "phone" | "sip" | "more"
conf.entry_points[0].pin         # str | None
```

### `Recurrence`

```python
recurrence.rules                 # list[str]  — RRULE/EXRULE/RDATE/EXDATE strings (RFC 5545)
recurrence.recurring_event_id    # str | None — parent event ID for instances
recurrence.original_start_time  # datetime | date | None
```

---

## Error handling

```python
from omnidapter.core.errors import (
    ConnectionNotFoundError,     # no credentials for connection_id
    UnsupportedCapabilityError,  # provider doesn't support the operation
    ProviderAPIError,            # provider returned an error response
    RateLimitError,              # 429; extends ProviderAPIError
    TokenRefreshError,           # token refresh failed
    TransportError,              # network-level failure
    OAuthStateError,             # OAuth state missing, expired, or tampered
    ScopeInsufficientError,      # connection lacks required scopes
)

try:
    event = await cal.get_event("primary", event_id)
except UnsupportedCapabilityError as e:
    print(f"Provider {e.provider_key} doesn't support get_event")
except RateLimitError as e:
    print(f"Rate limited. Retry after: {e.retry_after}s")
    print(f"Reset at: {e.rate_limit_reset}")
except ProviderAPIError as e:
    print(f"Provider error {e.status_code}: {e.response_body}")
    print(f"Correlation ID: {e.correlation_id}")
```

`ProviderAPIError` includes a `correlation_id` (a random ID generated per request) that you can log for tracing.
