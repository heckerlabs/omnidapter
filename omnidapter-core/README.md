# Omnidapter Core

Provider-agnostic async calendar integration library for Python.

`omnidapter` gives you one API surface for Google Calendar, Microsoft Outlook,
Zoho Calendar, Apple Calendar, and generic CalDAV servers.

## Installation

```bash
pip install omnidapter
```

## Quick Start

```python
from omnidapter import Omnidapter

omni = Omnidapter(
    credential_store=my_store,
    oauth_state_store=my_state_store,
)

conn = await omni.connection("conn_123")
cal = conn.calendar()

calendars = await cal.list_calendars()

async for event in cal.list_events("primary"):
    print(event.summary)
```

## Provider Keys

- `google`
- `microsoft`
- `zoho`
- `apple`
- `caldav` (manual registration)

## Core Documentation

- `docs/providers.md` - provider setup, OAuth wiring, custom providers
- `docs/calendar.md` - calendar capability matrix and method reference
- `docs/credential-stores.md` - production credential and OAuth state storage patterns

## Notes

- In-memory stores are for development only.
- Persist encrypted credentials for production.
- OAuth state storage must be shared across instances.

## License

MIT
