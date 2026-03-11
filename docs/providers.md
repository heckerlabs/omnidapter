# Provider Setup

Each provider requires different credentials and configuration. This guide covers setup for all built-in providers and shows how to wire the OAuth flow into a web application.

By default (`auto_register_by_env=True`), Omnidapter auto-registers OAuth providers only when their environment credentials are present. Apple auto-registration is opt-in via `OMNIDAPTER_ENABLE_APPLE=1`. You can always register providers manually (as shown below) to use constructor-based credentials.

---

## Google Calendar

**Auth:** OAuth 2.0 with PKCE
**Scopes:** Google Calendar API

### 1. Create OAuth credentials

1. Open [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → **APIs & Services** → **Enable APIs** → enable **Google Calendar API**
3. **Credentials** → **Create Credentials** → **OAuth 2.0 Client ID**
4. Application type: **Web application**
5. Add your redirect URI (e.g. `https://yourapp.com/oauth/google/callback`)
6. Copy **Client ID** and **Client Secret**

### 2. Register with Omnidapter

```python
from omnidapter.providers._base import OAuthConfig
from omnidapter.providers.google.provider import GoogleProvider

class ConfiguredGoogleProvider(GoogleProvider):
    def get_oauth_config(self) -> OAuthConfig:
        return OAuthConfig(
            client_id=os.environ["GOOGLE_CLIENT_ID"],
            client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
            authorization_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
            token_endpoint="https://oauth2.googleapis.com/token",
            default_scopes=[
                "https://www.googleapis.com/auth/calendar",
                "openid",
                "email",
            ],
            supports_pkce=True,
            extra_auth_params={"access_type": "offline", "prompt": "consent"},
        )

omni = Omnidapter(credential_store=..., oauth_state_store=...)
omni.register_provider(ConfiguredGoogleProvider())
```

`access_type=offline` and `prompt=consent` are required to receive a `refresh_token`. Google only returns a refresh token on first authorization unless `prompt=consent` forces re-consent.

### 3. OAuth flow

```python
# Step 1: Generate authorization URL
result = await omni.oauth.begin(
    provider="google",
    connection_id=str(uuid.uuid4()),    # generate and store this
    redirect_uri="https://yourapp.com/oauth/google/callback",
)
# Redirect the user to result.authorization_url
# Store result.connection_id → your user

# Step 2: Handle the callback
stored = await omni.oauth.complete(
    provider="google",
    connection_id=connection_id,        # retrieve from your session/DB
    code=request.query["code"],
    state=request.query["state"],
    redirect_uri="https://yourapp.com/oauth/google/callback",
)
# stored is persisted automatically — connection is ready
```

### 4. Scopes reference

| Scope | Access |
|---|---|
| `https://www.googleapis.com/auth/calendar` | Read + write all calendars |
| `https://www.googleapis.com/auth/calendar.readonly` | Read-only |
| `https://www.googleapis.com/auth/calendar.events` | Read + write events only |

---

## Microsoft Calendar (Outlook / Microsoft 365)

**Auth:** OAuth 2.0 with PKCE
**Scopes:** Microsoft Graph API

### 1. Register an app

1. Open [Azure Portal](https://portal.azure.com/) → **App registrations** → **New registration**
2. Name your app, choose **Accounts in any organizational directory and personal Microsoft accounts** (or restrict as needed)
3. Add a redirect URI under **Authentication** → **Web** (e.g. `https://yourapp.com/oauth/microsoft/callback`)
4. Under **Certificates & secrets** → create a **New client secret**
5. Copy **Application (client) ID** and the secret value

### 2. Register with Omnidapter

```python
from omnidapter.providers._base import OAuthConfig
from omnidapter.providers.microsoft.provider import MicrosoftProvider

TENANT = "common"  # or your tenant ID for single-tenant apps

class ConfiguredMicrosoftProvider(MicrosoftProvider):
    def get_oauth_config(self) -> OAuthConfig:
        return OAuthConfig(
            client_id=os.environ["MICROSOFT_CLIENT_ID"],
            client_secret=os.environ["MICROSOFT_CLIENT_SECRET"],
            authorization_endpoint=f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/authorize",
            token_endpoint=f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token",
            default_scopes=[
                "Calendars.ReadWrite",
                "offline_access",
                "openid",
                "email",
            ],
            supports_pkce=True,
        )

omni.register_provider(ConfiguredMicrosoftProvider())
```

`offline_access` is required to receive a refresh token.

### 3. OAuth flow

Same pattern as Google:

```python
result = await omni.oauth.begin(
    provider="microsoft",
    connection_id=str(uuid.uuid4()),
    redirect_uri="https://yourapp.com/oauth/microsoft/callback",
)

# On callback:
stored = await omni.oauth.complete(
    provider="microsoft",
    connection_id=connection_id,
    code=request.query["code"],
    state=request.query["state"],
    redirect_uri="https://yourapp.com/oauth/microsoft/callback",
)
```

### 4. Scopes reference

| Scope | Access |
|---|---|
| `Calendars.ReadWrite` | Read + write calendars and events |
| `Calendars.Read` | Read-only |
| `offline_access` | Required for refresh tokens |

---

## Zoho Calendar

**Auth:** OAuth 2.0 (no PKCE)
**Scopes:** Zoho Calendar API

### 1. Register an app

1. Open [Zoho API Console](https://api-console.zoho.com/)
2. **Add Client** → **Web Based** → fill in redirect URI
3. Copy **Client ID** and **Client Secret**

### 2. Register with Omnidapter

```python
from omnidapter.providers._base import OAuthConfig
from omnidapter.providers.zoho.provider import ZohoProvider

class ConfiguredZohoProvider(ZohoProvider):
    def get_oauth_config(self) -> OAuthConfig:
        return OAuthConfig(
            client_id=os.environ["ZOHO_CLIENT_ID"],
            client_secret=os.environ["ZOHO_CLIENT_SECRET"],
            authorization_endpoint="https://accounts.zoho.com/oauth/v2/auth",
            token_endpoint="https://accounts.zoho.com/oauth/v2/token",
            default_scopes=[
                "ZohoCalendar.calendar.ALL",
                "ZohoCalendar.event.ALL",
            ],
            supports_pkce=False,
            extra_auth_params={"access_type": "offline"},
        )

omni.register_provider(ConfiguredZohoProvider())
```

### 3. OAuth flow

```python
result = await omni.oauth.begin(
    provider="zoho",
    connection_id=str(uuid.uuid4()),
    redirect_uri="https://yourapp.com/oauth/zoho/callback",
)

stored = await omni.oauth.complete(
    provider="zoho",
    connection_id=connection_id,
    code=request.query["code"],
    state=request.query["state"],
    redirect_uri="https://yourapp.com/oauth/zoho/callback",
)
```

### 4. Scopes reference

| Scope | Access |
|---|---|
| `ZohoCalendar.calendar.ALL` | Full calendar access |
| `ZohoCalendar.event.ALL` | Full event access |
| `ZohoCalendar.calendar.READ` | Read-only calendar |
| `ZohoCalendar.event.READ` | Read-only events |

---

## Apple Calendar (iCloud)

**Auth:** HTTP Basic with an app-specific password
**No OAuth.** Apple requires an app-specific password rather than the account password.

### 1. Generate an app-specific password

1. Sign in at [appleid.apple.com](https://appleid.apple.com/)
2. **Sign-In and Security** → **App-Specific Passwords** → **Generate**
3. Label it (e.g. "My App"), copy the generated password (format: `xxxx-xxxx-xxxx-xxxx`)

### 2. Store credentials

No OAuth flow — store credentials directly:

```python
from omnidapter.auth.models import BasicCredentials
from omnidapter.core.metadata import AuthKind
from omnidapter.stores.credentials import StoredCredential

stored = StoredCredential(
    provider_key="apple",
    auth_kind=AuthKind.BASIC,
    credentials=BasicCredentials(
        username="user@icloud.com",
        password="abcd-efgh-ijkl-mnop",  # app-specific password
    ),
)

await omni.credential_store.save_credentials("conn_123", stored)
conn = await omni.connection("conn_123")
```

### Notes

- Apple's CalDAV endpoint is pre-configured (`https://caldav.icloud.com`). No `provider_config` needed.
- App-specific passwords do not expire but can be revoked at appleid.apple.com.
- Apple's iCloud CalDAV requires 2FA to be enabled on the Apple ID.

---

## CalDAV (self-hosted / other servers)

CalDAV is not registered by default. Register it for Nextcloud, Fastmail, Radicale, DAViCal, or any other CalDAV-compliant server.

### 1. Register the provider

```python
from omnidapter.providers.caldav.provider import CalDAVProvider

omni.register_provider(CalDAVProvider())
```

### 2. Store credentials

```python
stored = StoredCredential(
    provider_key="caldav",
    auth_kind=AuthKind.BASIC,
    credentials=BasicCredentials(username="user", password="pass"),
    provider_config={"server_url": "https://dav.fastmail.com/"},
)
await omni.credential_store.save_credentials("conn_123", stored)
```

### Known server URLs

| Server | URL pattern |
|---|---|
| Fastmail | `https://dav.fastmail.com/` |
| Nextcloud | `https://your.nextcloud.com/remote.php/dav/` |
| Radicale | `http://localhost:5232/` (default) |
| DAViCal | `https://your.server.com/davical/caldav.php/` |

---

## FastAPI integration example

A complete example wiring the OAuth flow into FastAPI:

```python
import uuid
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse

app = FastAPI()


@app.get("/connect/google")
async def connect_google(request: Request):
    connection_id = str(uuid.uuid4())
    # Store connection_id → current user in session/DB
    request.session["pending_connection_id"] = connection_id

    result = await omni.oauth.begin(
        provider="google",
        connection_id=connection_id,
        redirect_uri=str(request.url_for("google_callback")),
    )
    return RedirectResponse(result.authorization_url)


@app.get("/oauth/google/callback")
async def google_callback(request: Request, code: str, state: str):
    connection_id = request.session.pop("pending_connection_id")

    await omni.oauth.complete(
        provider="google",
        connection_id=connection_id,
        code=code,
        state=state,
        redirect_uri=str(request.url_for("google_callback")),
    )
    # Credentials are now persisted — store connection_id against the user
    return RedirectResponse("/dashboard")
```

---

## Custom providers

Implement `BaseProvider` to add any provider:

```python
from omnidapter.providers._base import BaseProvider, OAuthConfig
from omnidapter.core.metadata import ProviderMetadata, AuthKind, ServiceKind

class MyProvider(BaseProvider):
    @property
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider_key="myprovider",
            display_name="My Provider",
            services=[ServiceKind.CALENDAR],
            auth_kinds=[AuthKind.OAUTH2],
        )

    def get_oauth_config(self) -> OAuthConfig:
        return OAuthConfig(
            client_id=os.environ["MY_CLIENT_ID"],
            client_secret=os.environ["MY_CLIENT_SECRET"],
            authorization_endpoint="https://my.provider.com/oauth/authorize",
            token_endpoint="https://my.provider.com/oauth/token",
            default_scopes=["calendar:read", "calendar:write"],
        )

    async def exchange_code_for_tokens(self, connection_id, code, redirect_uri, code_verifier=None):
        # Exchange code, return StoredCredential
        ...

    async def refresh_token(self, stored):
        # Refresh token, return updated StoredCredential
        ...

    def get_calendar_service(self, connection_id, stored_credential, retry_policy=None, hooks=None):
        return MyCalendarService(connection_id, stored_credential, retry_policy, hooks)

omni.register_provider(MyProvider())
```

`get_calendar_service` should return a class inheriting from `CalendarService` and implementing all abstract methods.
