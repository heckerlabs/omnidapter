# Omnidapter

Provider-agnostic async calendar integration library for Python. Connect to Google Calendar, Microsoft Outlook, Zoho Calendar, or Apple Calendar with a single unified API.

## Installation

```bash
pip install omnidapter
```

## Quick start

```python
from omnidapter import Omnidapter

omni = Omnidapter(
    credential_store=my_store,
    oauth_state_store=my_state_store,
)

conn = await omni.connection("conn_123")
cal = conn.calendar()

# List calendars
calendars = await cal.list_calendars()

# Stream events
async for event in cal.list_events("primary"):
    print(event.summary, event.start)

# Create an event
from omnidapter.services.calendar.requests import CreateEventRequest
from datetime import datetime, timezone

event = await cal.create_event(CreateEventRequest(
    calendar_id="primary",
    summary="Team sync",
    start=datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc),
    end=datetime(2026, 3, 15, 11, 0, tzinfo=timezone.utc),
))
```

## Providers

| Provider | Key | Auth | Notes |
|---|---|---|---|
| Google Calendar | `google` | OAuth 2.0 + PKCE | |
| Microsoft / Outlook | `microsoft` | OAuth 2.0 + PKCE | |
| Zoho Calendar | `zoho` | OAuth 2.0 | |
| Apple / iCloud | `apple` | Basic (app-specific password) | Pre-configured CalDAV endpoint |
| CalDAV | `caldav` | Basic | Not registered by default. Bring your own server URL. |

Built-in registration is environment-aware by default (`auto_register_by_env=True`):
- OAuth providers are auto-registered only when both env vars are present:
  - Google: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
  - Microsoft: `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`
  - Zoho: `ZOHO_CLIENT_ID`, `ZOHO_CLIENT_SECRET`
- Apple is auto-registered only when `OMNIDAPTER_ENABLE_APPLE` is truthy (`1`, `true`, `yes`, `on`).

Set `auto_register_by_env=False` to register all built-ins regardless of env vars, or register providers manually for full control.

## Capabilities

| Capability | Google | Microsoft | Zoho | Apple | CalDAV* |
|---|:---:|:---:|:---:|:---:|:---:|
| List calendars | ✓ | ✓ | ✓ | ✓ | ✓ |
| Get calendar | ✓ | ✓ | ✓ | ✓ | ✓** |
| Create calendar | ✓ | ✓ | ✓ | ✓ | ✓** |
| Update calendar | ✓ | ✓ | ✓ | ✓ | ✓** |
| Delete calendar | ✓ | ✓ | ✓ | ✓ | ✓** |
| List events | ✓ | ✓ | ✓ | ✓ | ✓ |
| Get event | ✓ | ✓ | ✓ | ✓ | ✓ |
| Create event | ✓ | ✓ | ✓ | ✓ | ✓ |
| Update event | ✓ | ✓ | ✓ | ✓ | ✓ |
| Delete event | ✓ | ✓ | ✓ | ✓ | ✓ |
| Free/busy availability | ✓ | ✓ | — | — | — |
| Conference links | ✓ | ✓ | — | — | — |
| Recurrence (RRULE) | ✓ | ✓ | — | ✓ | ✓ |
| Attendees | ✓ | ✓ | ✓ | ✓ | ✓ |

*CalDAV requires manual registration via `omni.register_provider(CalDAVProvider())`.

Footnote `**`: CalDAV calendar collection CRUD depends on server policy. Some CalDAV servers reject `MKCALENDAR`/`MKCOL` (for example, Zoho's CalDAV sync endpoint), so top-level calendar create/delete may fail with `403/405/501` even when event CRUD works.

## OAuth flows

```python
# Step 1: Generate authorization URL
result = await omni.oauth.begin(
    provider="google",
    connection_id=str(uuid.uuid4()),
    redirect_uri="https://yourapp.com/oauth/google/callback",
)
# Redirect user to result.authorization_url

# Step 2: Handle callback
await omni.oauth.complete(
    provider="google",
    connection_id=connection_id,
    code=request.query["code"],
    state=request.query["state"],
    redirect_uri="https://yourapp.com/oauth/google/callback",
)
# Credentials persisted automatically
```

Tokens are refreshed automatically before expiry. Set `auto_refresh=False` to disable.

## Apple / iCloud

No OAuth. Use an [app-specific password](https://support.apple.com/en-us/102654):

```python
from omnidapter.auth.models import BasicCredentials
from omnidapter.core.metadata import AuthKind
from omnidapter.stores.credentials import StoredCredential

stored = StoredCredential(
    provider_key="apple",
    auth_kind=AuthKind.BASIC,
    credentials=BasicCredentials(
        username="user@icloud.com",
        password="abcd-efgh-ijkl-mnop",
    ),
)
await omni.credential_store.save_credentials("conn_123", stored)
```

## CalDAV (self-hosted)

```python
from omnidapter.providers.caldav.provider import CalDAVProvider

omni.register_provider(CalDAVProvider())

stored = StoredCredential(
    provider_key="caldav",
    auth_kind=AuthKind.BASIC,
    credentials=BasicCredentials(username="user", password="pass"),
    provider_config={"server_url": "https://dav.fastmail.com/"},
)

# Note: server-side method support varies. Some CalDAV servers disable
# MKCALENDAR/MKCOL and therefore do not allow creating calendars over CalDAV.
```

## Credential stores

The default in-memory stores are for development only. For production, implement `CredentialStore` and `OAuthStateStore`:

```python
from omnidapter.stores.credentials import CredentialStore, StoredCredential

class MyCredentialStore(CredentialStore):
    async def get_credentials(self, connection_id: str) -> StoredCredential | None: ...
    async def save_credentials(self, connection_id: str, credentials: StoredCredential) -> None: ...
    async def delete_credentials(self, connection_id: str) -> None: ...

omni = Omnidapter(credential_store=MyCredentialStore(), oauth_state_store=MyStateStore())
```

See [docs/credential-stores.md](docs/credential-stores.md) for a full guide including an encrypted SQLAlchemy implementation and a Redis OAuth state store.

## Checking capability support

```python
from omnidapter.services.calendar.capabilities import CalendarCapability

if cal.supports(CalendarCapability.GET_AVAILABILITY):
    result = await cal.get_availability(request)
```

## Custom providers

```python
from omnidapter.providers._base import BaseProvider

class MyProvider(BaseProvider):
    ...

omni.register_provider(MyProvider())
```

## Documentation

- [docs/providers.md](docs/providers.md) — OAuth app setup for each provider, FastAPI integration example, custom providers
- [docs/calendar.md](docs/calendar.md) — Full calendar API reference: all methods, return models, error handling
- [docs/credential-stores.md](docs/credential-stores.md) — Production stores: encryption, SQLAlchemy example, Redis OAuth state store

## Roadmap

**Webhooks / push notifications**
Real-time change notifications via Google Calendar push channels, Microsoft Graph subscriptions, and polling fallback for providers without native push support.

**Calendar-level CRUD**
Create, rename, delete, and share calendars — not just events.

**Common store implementations**
Official packages for popular backends: `omnidapter-sqlalchemy`, `omnidapter-redis`, `omnidapter-django`.

**New verticals**
CRM (contacts, deals, pipelines), Email (read/send/thread), Tasks — using the same provider + connection model.

## License

MIT
