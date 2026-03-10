# omnidapter

Provider-agnostic async calendar integration library for Python.

Omnidapter normalizes Google Calendar, Microsoft Calendar (Graph API), Zoho Calendar, and CalDAV behind a single typed interface. You wire up your own credential and OAuth state persistence; omnidapter handles the rest — OAuth flows, token refresh, retry, pagination, and provider-specific API translation.

---

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Architecture Overview](#architecture-overview)
- [Implementing the Stores](#implementing-the-stores)
  - [CredentialStore](#credentialstore)
  - [OAuthStateStore](#oauthstatestore)
- [Initializing Omnidapter](#initializing-omnidapter)
- [OAuth Flows](#oauth-flows)
  - [Beginning a Flow](#beginning-a-flow)
  - [Completing a Flow](#completing-a-flow)
- [Connecting to a Provider](#connecting-to-a-provider)
- [Calendar Operations](#calendar-operations)
  - [List Calendars](#list-calendars)
  - [List Events](#list-events)
  - [Get a Single Event](#get-a-single-event)
  - [Create an Event](#create-an-event)
  - [Update an Event](#update-an-event)
  - [Delete an Event](#delete-an-event)
  - [Check Availability](#check-availability)
  - [Webhooks / Push Notifications](#webhooks--push-notifications)
- [Pagination](#pagination)
- [Capabilities](#capabilities)
- [Provider Reference](#provider-reference)
  - [Google Calendar](#google-calendar)
  - [Microsoft Calendar](#microsoft-calendar)
  - [Zoho Calendar](#zoho-calendar)
  - [CalDAV](#caldav)
- [Data Models](#data-models)
  - [CalendarEvent](#calendarevent)
  - [Calendar](#calendar)
  - [Request Models](#request-models)
- [Error Handling](#error-handling)
- [Retry Policy](#retry-policy)
- [Provider Introspection](#provider-introspection)
- [Custom Providers](#custom-providers)
- [Testing](#testing)
  - [Fake Stores](#fake-stores)
  - [Contract Tests](#contract-tests)

---

## Installation

```bash
pip install omnidapter
```

Requires Python 3.10+.

---

## Quick Start

```python
import asyncio
from omnidapter import Omnidapter
from omnidapter.testing.fakes.stores import InMemoryCredentialStore, InMemoryOAuthStateStore

async def main():
    omni = Omnidapter(
        credential_store=InMemoryCredentialStore(),
        oauth_state_store=InMemoryOAuthStateStore(),
    )

    # Start an OAuth flow for Google
    result = await omni.oauth.begin(
        provider="google",
        connection_id="user-123",
        redirect_uri="https://myapp.com/oauth/callback",
    )
    print("Send the user to:", result.authorization_url)

    # After the user authorizes and you receive the callback:
    await omni.oauth.complete(
        provider="google",
        connection_id="user-123",
        code=request.query["code"],
        state=request.query["state"],
        redirect_uri="https://myapp.com/oauth/callback",
    )

    # Use the connection
    conn = await omni.connection("user-123")
    calendars = await conn.calendar().list_calendars()
    for cal in calendars:
        print(cal.summary, cal.calendar_id)

asyncio.run(main())
```

---

## Architecture Overview

```
Your Application
     │
     ▼
  Omnidapter                   ← composition root; you create one instance
     ├── CredentialStore        ← you implement; omnidapter reads/writes credentials
     ├── OAuthStateStore        ← you implement; stores transient OAuth state
     ├── ProviderRegistry       ← built-in providers registered automatically
     ├── OAuthHelper            ← begin/complete OAuth flows
     └── TokenRefreshManager    ← auto-refreshes expired tokens before each call
          │
          ▼
      Connection                ← per-request handle for a specific user+provider
          └── CalendarService   ← the typed service API
```

Omnidapter never owns a database. Your stores are the persistence layer. The library calls them during OAuth completion, token refresh, and connection resolution.

---

## Implementing the Stores

Both stores are async abstract base classes. You implement them once and inject them when constructing `Omnidapter`.

### CredentialStore

Persists credentials for each connection. Omnidapter calls this store when resolving connections, refreshing tokens, and completing OAuth flows.

```python
from omnidapter import CredentialStore, StoredCredential

class MyCredentialStore(CredentialStore):
    def __init__(self, db):
        self._db = db

    async def get_credentials(self, connection_id: str) -> StoredCredential | None:
        row = await self._db.fetch_one(
            "SELECT data FROM credentials WHERE id = $1", connection_id
        )
        if row is None:
            return None
        return StoredCredential.model_validate_json(row["data"])

    async def save_credentials(self, connection_id: str, credentials: StoredCredential) -> None:
        await self._db.execute(
            "INSERT INTO credentials (id, data) VALUES ($1, $2) "
            "ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data",
            connection_id,
            credentials.model_dump_json(),
        )

    async def delete_credentials(self, connection_id: str) -> None:
        await self._db.execute(
            "DELETE FROM credentials WHERE id = $1", connection_id
        )
```

**`StoredCredential` fields:**

| Field | Type | Description |
|---|---|---|
| `provider_key` | `str` | e.g. `"google"`, `"microsoft"` |
| `auth_kind` | `AuthKind` | `OAUTH2`, `API_KEY`, or `BASIC` |
| `credentials` | `OAuth2Credentials \| ApiKeyCredentials \| BasicCredentials` | The actual tokens/keys |
| `granted_scopes` | `list[str] \| None` | Scopes granted during OAuth |
| `provider_account_id` | `str \| None` | Provider user ID (e.g. Google user sub) |
| `provider_config` | `dict \| None` | Provider-specific config (e.g. CalDAV server URL) |

### OAuthStateStore

Persists transient OAuth state between the `begin` and `complete` steps. Entries are short-lived (typically 10 minutes).

```python
import json
from datetime import datetime
from omnidapter import OAuthStateStore

class MyOAuthStateStore(OAuthStateStore):
    def __init__(self, redis):
        self._redis = redis

    async def save_state(
        self,
        state_id: str,
        payload: dict,
        expires_at: datetime,
    ) -> None:
        ttl = int((expires_at - datetime.now(tz=expires_at.tzinfo)).total_seconds())
        await self._redis.setex(f"oauth_state:{state_id}", ttl, json.dumps(payload))

    async def load_state(self, state_id: str) -> dict | None:
        data = await self._redis.get(f"oauth_state:{state_id}")
        return json.loads(data) if data else None

    async def delete_state(self, state_id: str) -> None:
        await self._redis.delete(f"oauth_state:{state_id}")
```

---

## Initializing Omnidapter

```python
from omnidapter import Omnidapter
from omnidapter.transport.retry import RetryPolicy

omni = Omnidapter(
    credential_store=my_credential_store,
    oauth_state_store=my_oauth_state_store,

    # Optional: disable automatic token refresh before each call.
    # When False, calls may fail with TokenRefreshError if tokens are expired.
    auto_refresh=True,

    # Optional: configure HTTP retry behavior.
    retry_policy=RetryPolicy(max_retries=3, backoff_base=1.0, jitter=True),

    # Optional: called after credentials are written to the store,
    # e.g. to invalidate a cache. May be sync or async.
    on_credentials_updated=lambda conn_id, cred: print(f"Updated {conn_id}"),

    # Optional: set False to skip auto-registering built-in providers.
    register_builtins=True,
)
```

### Provider credentials via environment variables

Built-in OAuth providers read credentials from environment variables if not passed explicitly. Set these before starting your application:

| Provider | Variables |
|---|---|
| Google | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` |
| Microsoft | `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET` |
| Zoho | `ZOHO_CLIENT_ID`, `ZOHO_CLIENT_SECRET` |

Alternatively, pass them when registering the provider manually:

```python
from omnidapter.providers.google.provider import GoogleProvider

omni = Omnidapter(
    credential_store=...,
    oauth_state_store=...,
    register_builtins=False,
)
omni.register_provider(GoogleProvider(
    client_id="my-client-id",
    client_secret="my-client-secret",
))
```

---

## OAuth Flows

### Beginning a Flow

```python
result = await omni.oauth.begin(
    provider="google",          # or "microsoft", "zoho"
    connection_id="user-123",   # your ID for this user+account combination
    redirect_uri="https://myapp.com/oauth/callback",

    # Optional: override the default scopes for this connection.
    scopes=["https://www.googleapis.com/auth/calendar.readonly", "openid", "email"],

    # Optional: extra query parameters to add to the authorization URL.
    extra_params={"access_type": "offline", "prompt": "consent"},
)

# Redirect the user to:
print(result.authorization_url)

# result also contains:
# result.state         — the state parameter (stored internally)
# result.connection_id
# result.provider
```

PKCE is automatically applied for providers that support it (Google, Microsoft).

### Completing a Flow

Call this from your redirect URI handler after the provider redirects back:

```python
stored_credential = await omni.oauth.complete(
    provider="google",
    connection_id="user-123",
    code=request.params["code"],
    state=request.params["state"],
    redirect_uri="https://myapp.com/oauth/callback",
)
# Credentials are now persisted in your CredentialStore.
```

This validates the state, exchanges the code for tokens, and saves the resulting `StoredCredential`.

---

## Connecting to a Provider

Once credentials exist in the store, resolve a `Connection` to make API calls:

```python
conn = await omni.connection("user-123")
```

This:
1. Loads credentials from your `CredentialStore`
2. If `auto_refresh=True` and the token is expired (or within 60 seconds of expiry), refreshes it and saves the updated credentials
3. Returns a `Connection` handle

Raises `ConnectionNotFoundError` if no credentials exist for this ID.

---

## Calendar Operations

Access the calendar service from a connection:

```python
calendar = conn.calendar()
```

### List Calendars

```python
calendars = await calendar.list_calendars()
for cal in calendars:
    print(cal.calendar_id, cal.summary, "primary:", cal.is_primary)
```

### List Events

Use the async iterator to automatically page through all events:

```python
from datetime import datetime, timezone

async for event in calendar.list_events(
    calendar_id="primary",
    time_min=datetime(2024, 1, 1, tzinfo=timezone.utc),
    time_max=datetime(2024, 12, 31, tzinfo=timezone.utc),
    page_size=50,
):
    print(event.summary, event.start, event.end)
```

For manual page control, use `list_events_page`:

```python
page = await calendar.list_events_page(
    calendar_id="primary",
    time_min=datetime(2024, 1, 1, tzinfo=timezone.utc),
    page_size=25,
)
for event in page.items:
    print(event.summary)

if page.next_page_token:
    next_page = await calendar.list_events_page(
        calendar_id="primary",
        page_token=page.next_page_token,
        page_size=25,
    )
```

### Get a Single Event

```python
event = await calendar.get_event(calendar_id="primary", event_id="evt_abc123")
print(event.summary, event.start, event.end)
```

### Create an Event

```python
from datetime import datetime, timezone
from omnidapter import CreateEventRequest, Attendee

event = await calendar.create_event(CreateEventRequest(
    calendar_id="primary",
    summary="Team Sync",
    start=datetime(2024, 6, 15, 14, 0, tzinfo=timezone.utc),
    end=datetime(2024, 6, 15, 15, 0, tzinfo=timezone.utc),
    description="Weekly team check-in",
    location="Conference Room A",
    attendees=[
        Attendee(email="alice@example.com", display_name="Alice"),
        Attendee(email="bob@example.com"),
    ],
    timezone="America/New_York",
))
print("Created:", event.event_id)
```

**All-day event:**

```python
from datetime import date
from omnidapter import CreateEventRequest

event = await calendar.create_event(CreateEventRequest(
    calendar_id="primary",
    summary="Company Holiday",
    start=date(2024, 12, 25),
    end=date(2024, 12, 26),
    all_day=True,
))
```

**Recurring event:**

```python
from omnidapter import CreateEventRequest, Recurrence

event = await calendar.create_event(CreateEventRequest(
    calendar_id="primary",
    summary="Weekly Standup",
    start=datetime(2024, 6, 3, 9, 0, tzinfo=timezone.utc),
    end=datetime(2024, 6, 3, 9, 30, tzinfo=timezone.utc),
    recurrence=Recurrence(rules=["RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"]),
))
```

### Update an Event

Only set the fields you want to change; omitted fields remain unchanged:

```python
from omnidapter import UpdateEventRequest

updated = await calendar.update_event(UpdateEventRequest(
    calendar_id="primary",
    event_id="evt_abc123",
    summary="Team Sync (Updated)",
    location="Video Call",
))
```

### Delete an Event

```python
await calendar.delete_event(calendar_id="primary", event_id="evt_abc123")
```

### Check Availability

Query free/busy intervals across one or more calendars:

```python
from omnidapter import GetAvailabilityRequest

availability = await calendar.get_availability(GetAvailabilityRequest(
    calendar_ids=["primary", "work@example.com"],
    time_min=datetime(2024, 6, 15, 0, 0, tzinfo=timezone.utc),
    time_max=datetime(2024, 6, 16, 0, 0, tzinfo=timezone.utc),
    timezone="America/New_York",
))

for interval in availability.busy_intervals:
    print("Busy:", interval.start, "–", interval.end)
```

Supported by: Google, Microsoft. Check before calling:

```python
from omnidapter import CalendarCapability

if calendar.supports(CalendarCapability.GET_AVAILABILITY):
    availability = await calendar.get_availability(...)
```

### Webhooks / Push Notifications

Subscribe to push notifications for calendar changes (Google only in v1):

```python
from omnidapter import CreateWatchRequest, CalendarCapability

if calendar.supports(CalendarCapability.CREATE_WATCH):
    subscription = await calendar.create_watch(CreateWatchRequest(
        calendar_id="primary",
        webhook_url="https://myapp.com/webhooks/calendar",
        token="my-secret-verification-token",
    ))
    print("Subscription expires:", subscription.expiration)
```

Parse an incoming webhook in your handler:

```python
if calendar.supports(CalendarCapability.PARSE_WEBHOOK):
    notification = await calendar.parse_webhook(
        headers=dict(request.headers),
        body=await request.body(),
    )
    print("Resource changed:", notification)
```

---

## Pagination

`list_events` returns an async iterator that handles pagination automatically:

```python
async for event in calendar.list_events("primary"):
    process(event)
```

For manual control, use the lower-level `iter_pages` helper:

```python
from omnidapter.services.calendar.pagination import iter_pages

async for event in iter_pages(
    lambda token: calendar.list_events_page("primary", page_token=token)
):
    process(event)
```

Or work with raw pages yourself:

```python
page_token = None
while True:
    page = await calendar.list_events_page("primary", page_token=page_token)
    for event in page.items:
        process(event)
    if page.next_page_token is None:
        break
    page_token = page.next_page_token
```

---

## Capabilities

Providers differ in what they support. Use `supports()` before calling optional features, or let omnidapter raise `UnsupportedCapabilityError` automatically.

```python
from omnidapter import CalendarCapability

# Check before calling
if calendar.supports(CalendarCapability.GET_AVAILABILITY):
    result = await calendar.get_availability(...)

# Inspect all supported capabilities
print(calendar.capabilities)
# frozenset({'list_calendars', 'create_event', 'update_event', ...})
```

**`CalendarCapability` values:**

| Capability | Description |
|---|---|
| `LIST_CALENDARS` | List accessible calendars |
| `LIST_EVENTS` | Page through events |
| `GET_EVENT` | Fetch a single event |
| `CREATE_EVENT` | Create events |
| `UPDATE_EVENT` | Update events |
| `DELETE_EVENT` | Delete events |
| `GET_AVAILABILITY` | Free/busy queries |
| `CREATE_WATCH` | Subscribe to push notifications |
| `PARSE_WEBHOOK` | Parse incoming webhook payloads |
| `CONFERENCE_LINKS` | Video conference data on events |
| `RECURRENCE` | Recurring event support |
| `ATTENDEES` | Attendee management |

---

## Provider Reference

### Google Calendar

- **Provider key:** `"google"`
- **Auth:** OAuth 2.0 with PKCE
- **Authorization endpoint:** `https://accounts.google.com/o/oauth2/v2/auth`
- **Token endpoint:** `https://oauth2.googleapis.com/token`
- **Default scopes:** `https://www.googleapis.com/auth/calendar`, `openid`, `email`
- **Capabilities:** All capabilities including `GET_AVAILABILITY`, `CREATE_WATCH`, `PARSE_WEBHOOK`, `CONFERENCE_LINKS`

**Setup:**
```bash
export GOOGLE_CLIENT_ID="..."
export GOOGLE_CLIENT_SECRET="..."
```

In Google Cloud Console: enable the **Google Calendar API** and configure an OAuth 2.0 client with your redirect URI.

### Microsoft Calendar

- **Provider key:** `"microsoft"`
- **Auth:** OAuth 2.0 with PKCE
- **Authorization endpoint:** `https://login.microsoftonline.com/common/oauth2/v2.0/authorize`
- **Token endpoint:** `https://login.microsoftonline.com/common/oauth2/v2.0/token`
- **Default scopes:** `Calendars.ReadWrite`, `offline_access`, `openid`, `email`
- **Capabilities:** All capabilities except `CREATE_WATCH` and `PARSE_WEBHOOK`

**Setup:**
```bash
export MICROSOFT_CLIENT_ID="..."
export MICROSOFT_CLIENT_SECRET="..."
```

In Azure Portal: register an app, add `Calendars.ReadWrite` delegated permission, and add your redirect URI.

### Zoho Calendar

- **Provider key:** `"zoho"`
- **Auth:** OAuth 2.0 (no PKCE)
- **Authorization endpoint:** `https://accounts.zoho.com/oauth/v2/auth`
- **Token endpoint:** `https://accounts.zoho.com/oauth/v2/token`
- **Default scopes:** `ZohoCalendar.calendar.ALL`, `ZohoCalendar.event.ALL`
- **Capabilities:** `LIST_CALENDARS`, `LIST_EVENTS`, `GET_EVENT`, `CREATE_EVENT`, `UPDATE_EVENT`, `DELETE_EVENT`, `ATTENDEES`

**Setup:**
```bash
export ZOHO_CLIENT_ID="..."
export ZOHO_CLIENT_SECRET="..."
```

In Zoho API Console: register a server-based application and add your redirect URI.

### CalDAV

- **Provider key:** `"caldav"`
- **Auth:** HTTP Basic authentication
- **Capabilities:** `LIST_CALENDARS`, `LIST_EVENTS`, `GET_EVENT`, `CREATE_EVENT`, `UPDATE_EVENT`, `DELETE_EVENT`, `RECURRENCE`, `ATTENDEES`

CalDAV does not use OAuth. Store credentials directly before resolving a connection:

```python
from omnidapter import StoredCredential, BasicCredentials, AuthKind

stored = StoredCredential(
    provider_key="caldav",
    auth_kind=AuthKind.BASIC,
    credentials=BasicCredentials(
        username="user@example.com",
        password="app-specific-password",
    ),
    provider_config={
        "server_url": "https://caldav.fastmail.com/dav/",
    },
)
await credential_store.save_credentials("user-123", stored)

conn = await omni.connection("user-123")
```

Compatible servers: Fastmail, iCloud (app passwords), Nextcloud, Radicale, Baikal.

---

## Data Models

### CalendarEvent

```python
class CalendarEvent:
    event_id: str
    calendar_id: str
    summary: str | None
    description: str | None
    location: str | None
    status: EventStatus           # CONFIRMED | TENTATIVE | CANCELLED | UNKNOWN
    visibility: EventVisibility   # PUBLIC | PRIVATE | CONFIDENTIAL | DEFAULT
    start: datetime | date        # datetime = timed event; date = all-day
    end: datetime | date
    all_day: bool
    timezone: str | None
    organizer: Organizer | None
    attendees: list[Attendee]
    recurrence: Recurrence | None
    conference_data: ConferenceData | None
    reminders: Reminder | None
    created_at: datetime | None
    updated_at: datetime | None
    html_link: str | None
    ical_uid: str | None
    etag: str | None
    sequence: int | None
    provider_data: dict | None    # raw provider fields; not covered by semver
```

### Calendar

```python
class Calendar:
    calendar_id: str
    summary: str
    description: str | None
    timezone: str | None
    is_primary: bool
    is_read_only: bool
    background_color: str | None
    foreground_color: str | None
    provider_data: dict | None
```

### Request Models

**`CreateEventRequest`** — required: `calendar_id`, `summary`, `start`, `end`. All other fields are optional.

**`UpdateEventRequest`** — required: `calendar_id`, `event_id`. All other fields are optional; omitted fields are left unchanged.

**`GetAvailabilityRequest`** — required: `calendar_ids`, `time_min`, `time_max`.

**`CreateWatchRequest`** — required: `calendar_id`, `webhook_url`.

Pass provider-specific parameters that aren't in the normalized model using the `extra` dict:

```python
CreateEventRequest(
    calendar_id="primary",
    summary="My Event",
    start=...,
    end=...,
    extra={"source": {"title": "My App", "url": "https://myapp.com"}},
)
```

---

## Error Handling

All exceptions inherit from `OmnidapterError`.

```python
from omnidapter import (
    OmnidapterError,
    ConnectionNotFoundError,
    AuthError,
    TokenRefreshError,
    OAuthStateError,
    UnsupportedCapabilityError,
    ScopeInsufficientError,
    ProviderAPIError,
    RateLimitError,
    TransportError,
    InvalidCredentialFormatError,
)

try:
    conn = await omni.connection("user-123")
    events = [e async for e in conn.calendar().list_events("primary")]

except ConnectionNotFoundError as e:
    # No credentials found for this connection_id
    print("Unknown connection:", e.connection_id)

except TokenRefreshError as e:
    # Refresh failed — user probably revoked access
    print(f"Refresh failed for {e.provider_key}:", e)
    # Re-prompt the user for authorization

except ScopeInsufficientError as e:
    # The connection doesn't have the required scopes
    print("Missing scopes:", e.required_scopes)

except RateLimitError as e:
    # Provider rate-limited the request
    print(f"Rate limited. Retry after: {e.retry_after}s")

except ProviderAPIError as e:
    # Provider returned an error response
    print(f"API error {e.status_code} from {e.provider_key}: {e}")
    print("Correlation ID:", e.correlation_id)

except UnsupportedCapabilityError as e:
    # Called a method the provider doesn't support
    print(f"{e.provider_key} does not support {e.capability}")

except TransportError as e:
    # Network-level failure (DNS, timeout, connection refused)
    print("Network error:", e)
```

**Exception reference:**

| Exception | When raised |
|---|---|
| `ConnectionNotFoundError` | No credentials for the given connection ID |
| `TokenRefreshError` | Access token refresh failed (e.g. revoked) |
| `OAuthStateError` | OAuth state missing, expired, or tampered |
| `ScopeInsufficientError` | Connection lacks required OAuth scopes |
| `InvalidCredentialFormatError` | Stored credentials don't match the expected format |
| `UnsupportedCapabilityError` | Called a method the provider doesn't support |
| `ProviderAPIError` | Provider returned an error HTTP response |
| `RateLimitError` | Provider returned HTTP 429 (subclass of `ProviderAPIError`) |
| `TransportError` | Network-level failure |
| `AuthError` | Base class for auth-related errors |
| `OmnidapterError` | Base class for all library errors |

---

## Retry Policy

Configure HTTP retry behavior when constructing `Omnidapter`:

```python
from omnidapter.transport.retry import RetryPolicy

# Default: 3 retries, exponential backoff, jitter, retries on 429/5xx
policy = RetryPolicy.default()

# No retries
policy = RetryPolicy.no_retry()

# Custom policy
policy = RetryPolicy(
    max_retries=5,
    backoff_base=2.0,      # seconds; doubles each attempt
    backoff_max=30.0,      # cap in seconds
    retry_on_status=frozenset({429, 500, 502, 503, 504}),
    retry_on_network_error=True,
    jitter=True,           # adds random variation to avoid thundering herd
)

omni = Omnidapter(..., retry_policy=policy)
```

Backoff for attempt `n` (0-indexed): `min(backoff_base * 2^n, backoff_max)` plus optional jitter.

---

## Provider Introspection

Inspect registered providers at runtime:

```python
# List all registered provider keys
print(omni.list_providers())
# ['google', 'microsoft', 'zoho', 'caldav']

# Get full metadata for a provider
meta = omni.describe_provider("google")
print(meta.display_name)                    # "Google Calendar"
print(meta.auth_kinds)                      # [<AuthKind.OAUTH2: 'oauth2'>]
print(meta.oauth.authorization_endpoint)    # "https://accounts.google.com/..."
print(meta.capabilities)                    # {'calendar': ['list_calendars', ...]}

# OAuth scope groups (for building a scope selection UI)
for group in meta.oauth.scope_groups:
    print(group.name, "→", group.scopes)
```

---

## Custom Providers

Implement `BaseProvider` to add your own provider:

```python
from omnidapter.providers._base import BaseProvider, OAuthConfig
from omnidapter.core.metadata import (
    ProviderMetadata, AuthKind, ServiceKind, OAuthMetadata
)
from omnidapter.stores.credentials import StoredCredential
from omnidapter.services.calendar.interface import CalendarService
from omnidapter.services.calendar.capabilities import CalendarCapability

class AcmeProvider(BaseProvider):
    def __init__(self, client_id: str, client_secret: str):
        self._client_id = client_id
        self._client_secret = client_secret

    @property
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider_key="acme",
            display_name="Acme Calendar",
            services=[ServiceKind.CALENDAR],
            auth_kinds=[AuthKind.OAUTH2],
            oauth=OAuthMetadata(
                authorization_endpoint="https://acme.example.com/oauth/authorize",
                token_endpoint="https://acme.example.com/oauth/token",
                supports_pkce=True,
                default_scopes=["calendar:read", "calendar:write"],
            ),
            capabilities={
                "calendar": [
                    CalendarCapability.LIST_CALENDARS.value,
                    CalendarCapability.LIST_EVENTS.value,
                    CalendarCapability.CREATE_EVENT.value,
                ]
            },
        )

    def get_oauth_config(self) -> OAuthConfig:
        return OAuthConfig(
            client_id=self._client_id,
            client_secret=self._client_secret,
            authorization_endpoint="https://acme.example.com/oauth/authorize",
            token_endpoint="https://acme.example.com/oauth/token",
            supports_pkce=True,
        )

    async def exchange_code_for_tokens(
        self,
        connection_id: str,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> StoredCredential:
        # Exchange code for tokens and return StoredCredential
        ...

    async def refresh_token(self, stored: StoredCredential) -> StoredCredential:
        # Refresh and return an updated StoredCredential
        ...

    def get_calendar_service(
        self,
        connection_id: str,
        stored_credential: StoredCredential,
        retry_policy=None,
        hooks=None,
    ) -> CalendarService:
        return AcmeCalendarService(connection_id, stored_credential, retry_policy)


omni.register_provider(AcmeProvider(client_id="...", client_secret="..."))
```

---

## Testing

### Fake Stores

For unit tests, use the in-memory store implementations included in `omnidapter.testing`:

```python
from omnidapter import Omnidapter, StoredCredential, OAuth2Credentials, AuthKind
from omnidapter.testing.fakes.stores import InMemoryCredentialStore, InMemoryOAuthStateStore
from datetime import datetime, timezone, timedelta

async def test_list_calendars():
    cred_store = InMemoryCredentialStore()
    state_store = InMemoryOAuthStateStore()

    # Pre-seed credentials to skip the OAuth flow in tests
    cred_store.seed("conn-1", StoredCredential(
        provider_key="google",
        auth_kind=AuthKind.OAUTH2,
        credentials=OAuth2Credentials(
            access_token="test-token",
            expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=1),
        ),
    ))

    omni = Omnidapter(credential_store=cred_store, oauth_state_store=state_store)
    conn = await omni.connection("conn-1")
    # Make assertions against a mocked HTTP layer ...
```

`InMemoryCredentialStore` also exposes `.seed(connection_id, stored_credential)` to directly inject credentials without going through the full OAuth flow.

### Contract Tests

Verify that a custom `CalendarService` implementation satisfies the expected interface contract:

```python
import pytest
from omnidapter.testing.contracts.calendar import CalendarProviderContract

class TestAcmeCalendarService(CalendarProviderContract):
    @pytest.fixture
    def calendar_service(self):
        return AcmeCalendarService(
            connection_id="test",
            stored_credential=make_test_credential(),
        )
    # All contract assertions run automatically
```

The contract suite verifies:
- `capabilities` returns a `frozenset` of valid `CalendarCapability` values
- `supports()` is consistent with `capabilities`
- Methods for unsupported capabilities raise `UnsupportedCapabilityError`
- `list_events_page` returns a typed `Page` object when `LIST_EVENTS` is supported
- `_provider_key` returns a non-empty string
- Batch capabilities (reserved for a future version) are not claimed as supported
