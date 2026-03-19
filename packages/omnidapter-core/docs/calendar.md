# Calendar API

Calendar operations are accessed from a connection:

```python
conn = await omni.connection("conn_123")
cal = conn.calendar()
```

## Core Operations

- `list_calendars()`
- `get_calendar(calendar_id)`
- `create_calendar(request)`
- `update_calendar(request)`
- `delete_calendar(calendar_id)`
- `list_events(calendar_id, ...)`
- `get_event(calendar_id, event_id)`
- `create_event(request)`
- `update_event(request)`
- `delete_event(calendar_id, event_id)`
- `get_availability(request)` (provider-dependent)

## Capability Checks

Use capability checks before optional features:

```python
from omnidapter.services.calendar.capabilities import CalendarCapability

if cal.supports(CalendarCapability.GET_AVAILABILITY):
    result = await cal.get_availability(req)
```

## Provider Support Highlights

- Google / Microsoft: broad feature support, including availability
- Zoho: no availability API
- Apple / CalDAV: feature support varies by server/provider behavior

## Error Types

- `ConnectionNotFoundError`
- `UnsupportedCapabilityError`
- `ProviderAPIError`
- `RateLimitError`
- `TokenRefreshError`
- `TransportError`
- `OAuthStateError`
