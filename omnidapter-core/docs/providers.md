# Provider Setup

This guide covers built-in provider setup for Omnidapter Core.

## Google

- Auth: OAuth 2.0 + PKCE
- Env vars: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
- Typical scopes: `https://www.googleapis.com/auth/calendar`

## Microsoft

- Auth: OAuth 2.0 + PKCE
- Env vars: `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`
- Typical scopes: `Calendars.ReadWrite`, `offline_access`

## Zoho

- Auth: OAuth 2.0
- Env vars: `ZOHO_CLIENT_ID`, `ZOHO_CLIENT_SECRET`

## Apple

- Auth: Basic (app-specific password)
- No OAuth callback flow
- Env vars: `OMNIDAPTER_APPLE_ENABLED`

## CalDAV

- Auth: Basic
- Not auto-registered by default
- Register manually with `CalDAVProvider()`

## OAuth Flow Pattern

```python
result = await omni.oauth.begin(
    provider="google",
    connection_id="<id>",
    redirect_uri="https://yourapp.com/oauth/google/callback",
)

await omni.oauth.complete(
    provider="google",
    connection_id="<id>",
    code=request.query["code"],
    state=request.query["state"],
    redirect_uri="https://yourapp.com/oauth/google/callback",
)
```

## Auto Registration

With `auto_register_by_env=True` (default), OAuth providers are registered only
when corresponding env credentials are present.
