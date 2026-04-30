# Omnidapter Core

Provider-agnostic async calendar and booking integration library for Python.

`omnidapter` gives you one API surface for Google Calendar, Microsoft Outlook,
Zoho Calendar, Apple Calendar, generic CalDAV servers, Acuity Scheduling,
Cal.com, Square Appointments, Calendly, Microsoft Bookings, Jobber, and
Housecall Pro.

## Installation

```bash
pip install omnidapter
```

## Quick Start

### Calendar

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

### Booking

```python
from datetime import datetime, timezone
from omnidapter import Omnidapter, CreateBookingRequest, BookingCustomer

omni = Omnidapter(credential_store=my_store, oauth_state_store=my_state_store)

conn = await omni.connection("acuity_conn_1")
bk = conn.booking()

# Discover services and availability
services = await bk.list_services()
slots = await bk.get_availability(
    service_id=services[0].id,
    start=datetime(2026, 6, 1, tzinfo=timezone.utc),
    end=datetime(2026, 6, 7, tzinfo=timezone.utc),
)

# Book a slot
booking = await bk.create_booking(CreateBookingRequest(
    service_id=services[0].id,
    start=slots[0].start,
    customer=BookingCustomer(name="Jane Doe", email="jane@example.com"),
))
print(f"Booked: {booking.id} at {booking.start}")

# Cancel if needed
await bk.cancel_booking(booking.id)
```

## Provider Keys

### Calendar providers
- `google`
- `microsoft`
- `zoho`
- `apple`
- `caldav` (manual registration)

### Booking providers
- `acuity`
- `calcom`
- `square`
- `calendly`
- `microsoft` (also supports `ServiceKind.BOOKING` via Microsoft Bookings Graph API)
## Core Documentation

- `docs/providers.md` — provider setup, OAuth wiring, custom providers
- `docs/calendar.md` — calendar capability matrix and method reference
- `docs/booking.md` — booking capability matrix and method reference
- `docs/credential-stores.md` — production credential and OAuth state storage patterns

## Notes

- In-memory stores are for development only.
- Persist encrypted credentials for production.
- OAuth state storage must be shared across instances.
- Use `services=["booking"]` when creating a connection to scope OAuth authorization to booking only. Omit to request all services the provider supports.

## License

MIT
