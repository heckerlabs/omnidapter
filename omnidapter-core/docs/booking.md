# Booking API

Booking operations are accessed from a connection:

```python
conn = await omni.connection("conn_123")
bk = conn.booking()
```

`conn.booking()` raises `UnsupportedCapabilityError` if the provider does not
support `ServiceKind.BOOKING`, and `ServiceAuthorizationError` if the connection
was not authorized for booking (i.e. `services=["booking"]` was not requested
at authorization time).

---

## Capability Matrix

| Capability | Acuity | Cal.com | Square | Calendly | MS Bookings | Zoho Bookings |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| `LIST_SERVICES` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `LIST_STAFF` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `LIST_LOCATIONS` | ❌ | ✅ | ✅ | ❌ | ✅ | ❌ |
| `GET_AVAILABILITY` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `CREATE_BOOKING` | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ |
| `CANCEL_BOOKING` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `RESCHEDULE_BOOKING` | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ |
| `UPDATE_BOOKING` | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ |
| `LIST_BOOKINGS` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `CUSTOMER_LOOKUP` | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ |
| `CUSTOMER_MANAGEMENT` | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ |
| `MULTI_LOCATION` | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ |
| `MULTI_STAFF` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `MULTI_SERVICE` | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |

`WEBHOOKS` is reserved and not claimed by any v1 provider.

Calendly's API is read-only — it supports listing event types and scheduled
events but does not expose an endpoint to create bookings directly.

---

## Capability Checks

Always check before calling optional operations:

```python
from omnidapter.services.booking.capabilities import BookingCapability

if bk.supports(BookingCapability.CREATE_BOOKING):
    booking = await bk.create_booking(req)

if bk.supports(BookingCapability.LIST_LOCATIONS):
    locations = await bk.list_locations()
```

Calling an unsupported method raises `UnsupportedCapabilityError`.

---

## Method Reference

### Services

```python
services: list[ServiceType] = await bk.list_services()
service: ServiceType = await bk.get_service_type(service_id)
```

`ServiceType` fields: `id`, `name`, `description`, `duration_minutes`, `price`,
`provider_data`.

### Staff

```python
staff: list[StaffMember] = await bk.list_staff(service_id=None, location_id=None)
member: StaffMember = await bk.get_staff(staff_id)
```

`StaffMember` fields: `id`, `name`, `email`, `service_ids`, `provider_data`.

### Locations

```python
locations: list[BookingLocation] = await bk.list_locations()
```

`BookingLocation` fields: `id`, `name`, `address`, `provider_data`.

### Availability

```python
from datetime import datetime, timezone

slots: list[AvailabilitySlot] = await bk.get_availability(
    service_id="svc-1",
    start=datetime(2026, 6, 1, tzinfo=timezone.utc),
    end=datetime(2026, 6, 7, tzinfo=timezone.utc),
    staff_id=None,       # optional
    location_id=None,    # optional
    timezone="UTC",      # optional
)
```

`AvailabilitySlot` fields: `start`, `end`, `staff_id`, `location_id`,
`service_id`.

### Create Booking

```python
from omnidapter import CreateBookingRequest, BookingCustomer

booking: Booking = await bk.create_booking(CreateBookingRequest(
    service_id="svc-1",
    start=slots[0].start,
    customer=BookingCustomer(name="Jane Doe", email="jane@example.com"),
    staff_id=None,       # optional
    location_id=None,    # optional
    notes=None,          # optional
))
```

For providers that require a pre-existing customer record (Square, Microsoft
Bookings), `create_booking` calls `find_customer` then
`create_customer` automatically if the customer is not found.

Pass `customer=BookingCustomer(id="existing-id")` to bypass the find-or-create
step entirely.

`Booking` fields: `id`, `service_id`, `start`, `end`, `status`, `customer`,
`staff_id`, `location_id`, `notes`, `management_urls`, `provider_data`.

`management_urls` is a `dict[str, str]` with well-known keys `"cancel"`,
`"reschedule"`, `"manage"`, `"confirm"` where the provider exposes them
(Calendly populates these from invitee URLs).

### Get / List Bookings

```python
booking: Booking = await bk.get_booking(booking_id)

from omnidapter import ListBookingsRequest

async for booking in bk.list_bookings(ListBookingsRequest(
    start=datetime(2026, 6, 1, tzinfo=timezone.utc),
    end=datetime(2026, 6, 30, tzinfo=timezone.utc),
    status=None,           # optional BookingStatus filter
    customer_email=None,   # optional
    staff_id=None,         # optional
    service_id=None,       # optional
    page_size=100,         # optional
)):
    print(booking.id)
```

`list_bookings` returns an `AsyncIterator` — pagination is handled
transparently inside each provider implementation.

### Update / Reschedule / Cancel

```python
from omnidapter import UpdateBookingRequest, RescheduleBookingRequest

updated: Booking = await bk.update_booking(UpdateBookingRequest(
    booking_id="bk-1",
    start=new_start,     # optional
    staff_id=None,       # optional
    notes=None,          # optional
))

rescheduled: Booking = await bk.reschedule_booking(RescheduleBookingRequest(
    booking_id="bk-1",
    new_start=new_start,
    new_staff_id=None,   # optional
))

await bk.cancel_booking(booking_id, reason=None)
```

### Customer Management

```python
from omnidapter import FindCustomerRequest

customer: BookingCustomer | None = await bk.find_customer(
    FindCustomerRequest(email="jane@example.com")
)

customer: BookingCustomer = await bk.get_customer(customer_id)

new_customer: BookingCustomer = await bk.create_customer(
    BookingCustomer(name="Jane Doe", email="jane@example.com")
)
```

---

## Error Types

| Exception | When raised |
|---|---|
| `UnsupportedCapabilityError` | Method called on a provider that doesn't support it |
| `ServiceAuthorizationError` | Connection was not authorized for `ServiceKind.BOOKING` |
| `SlotUnavailableError` | Slot taken between `get_availability` and `create_booking` |
| `CustomerResolutionError` | Find-or-create customer failed during booking creation |
| `ProviderAPIError` | Provider returned an error HTTP response |
| `RateLimitError` | Provider rate-limited the request (extends `ProviderAPIError`) |
| `TokenRefreshError` | Access token could not be refreshed |
| `TransportError` | Network-level failure |

---

## Provider Notes

**Acuity Scheduling** — "calendars" are staff members in the Acuity model.
`list_staff()` maps to `GET /calendars`. Rate limit: 10 req/s.

**Cal.com** — All requests require the `cal-api-version: 2024-08-13` header,
sent automatically. Rescheduled bookings get a new UID. `MULTI_SERVICE` allows
booking multiple event types in one call.

**Square Appointments** — `create_booking` fetches `service_variation_version`
from the Catalog API before creating the booking (Square requires it). An
idempotency key is generated automatically. Cancel requires fetching the current
`version` first.

**Calendly** — Read-only. `list_services` returns event types, `list_bookings`
returns scheduled events (invitees), and `cancel_booking` calls the cancel
endpoint. `management_urls` on bookings contains Calendly's hosted cancel and
reschedule URLs.

**Microsoft Bookings** — Requires a `business_id` (the booking business email
address) in `provider_config` on the stored credential. Use the
`OMNIDAPTER_TEST_MSBOOKINGS_BUSINESS_ID` env var in integration tests.
Availability is queried via `POST .../getStaffAvailability`.

**Zoho Bookings** — `Zoho-oauthtoken` auth header. All list operations require
a `workspace_id`; if not set in `provider_config`, the first available workspace
is fetched automatically. Customer creation is implicit (via booking creation)
— `CUSTOMER_MANAGEMENT` is not supported.
