# Omnidapter

Provider-agnostic async calendar integration library for Python. Connect to Google Calendar, Microsoft Outlook, Zoho Calendar, or Apple Calendar with a single unified API.

## Installation

```bash
pip install omnidapter
```

## Quick start

```python
from omnidapter import Omnidapter, StoredCredential, OAuth2Credentials
from omnidapter.core.metadata import AuthKind

omni = Omnidapter(
    credential_store=my_store,
    oauth_state_store=my_state_store,
)

# List calendars
conn = await omni.connection("conn_123")
calendars = await conn.calendar().list_calendars()

# List events
async for event in conn.calendar().list_events(calendar_id="primary"):
    print(event.summary, event.start)

# Create an event
from omnidapter import CreateEventRequest
from datetime import datetime, timezone

event = await conn.calendar().create_event(CreateEventRequest(
    calendar_id="primary",
    summary="Team sync",
    start=datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc),
    end=datetime(2026, 3, 15, 11, 0, tzinfo=timezone.utc),
))
```

## Storing credentials

```python
from omnidapter import StoredCredential, OAuth2Credentials
from omnidapter.core.metadata import AuthKind

stored = StoredCredential(
    provider_key="google",
    auth_kind=AuthKind.OAUTH2,
    credentials=OAuth2Credentials(
        access_token="ya29...",
        refresh_token="1//...",
        expires_at=datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc),
    ),
)
await omni.credential_store.save("conn_123", stored)
```

## Providers

| Key           | Auth          | Notes                                 |
|---------------|---------------|---------------------------------------|
| `google`      | OAuth 2.0     | Google Calendar                       |
| `microsoft`   | OAuth 2.0     | Microsoft Graph / Outlook Calendar    |
| `zoho`        | OAuth 2.0     | Zoho Calendar                         |
| `apple`       | Basic (app-specific password) | iCloud Calendar via CalDAV |

### Apple / iCloud

```python
from omnidapter import StoredCredential, BasicCredentials
from omnidapter.core.metadata import AuthKind

stored = StoredCredential(
    provider_key="apple",
    auth_kind=AuthKind.BASIC,
    credentials=BasicCredentials(
        username="user@icloud.com",
        password="abcd-efgh-ijkl-mnop",  # app-specific password
    ),
)
```

### Custom CalDAV server

CalDAV is not registered by default. Register it manually for self-hosted servers (Nextcloud, Fastmail, Radicale, etc.):

```python
from omnidapter.providers.caldav.provider import CalDAVProvider

omni.register_provider(CalDAVProvider())

stored = StoredCredential(
    provider_key="caldav",
    auth_kind=AuthKind.BASIC,
    credentials=BasicCredentials(username="user", password="pass"),
    provider_config={"server_url": "https://dav.fastmail.com/"},
)
```

## OAuth flows

```python
# Start the OAuth flow
url, state = await omni.oauth.authorization_url("google", redirect_uri="https://example.com/callback")

# Complete the flow after redirect
stored = await omni.oauth.exchange_code(
    provider_key="google",
    code=request.query["code"],
    state=request.query["state"],
    redirect_uri="https://example.com/callback",
)
await omni.credential_store.save("conn_123", stored)
```

Tokens are refreshed automatically before expiry. Set `auto_refresh=False` on `Omnidapter` to disable.

## Custom credential stores

Implement `CredentialStore` and `OAuthStateStore` to persist credentials in your database:

```python
from omnidapter import CredentialStore, StoredCredential

class MyCredentialStore(CredentialStore):
    async def get_credentials(self, connection_id: str) -> StoredCredential | None:
        ...

    async def save(self, connection_id: str, credential: StoredCredential) -> None:
        ...

    async def delete(self, connection_id: str) -> None:
        ...

omni = Omnidapter(credential_store=MyCredentialStore())
```

## Custom providers

```python
from omnidapter.providers._base import BaseProvider

class MyProvider(BaseProvider):
    ...

omni.register_provider(MyProvider())
```

## License

MIT
