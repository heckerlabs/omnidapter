# OAuth Flows

Omnidapter API hosts the OAuth 2.0 flow on behalf of your organization's
end-users. You initiate the flow, redirect your user, and receive a callback
when it's done.

---

## Supported Providers

| Provider | Auth Kind | Key |
|---|---|---|
| Google Calendar | OAuth 2.0 PKCE | `google` |
| Microsoft Outlook | OAuth 2.0 PKCE | `microsoft` |
| Zoho Calendar | OAuth 2.0 | `zoho` |
| CalDAV servers | Username/password | `caldav` |

---

## OAuth Flow Overview

```
Your App          Omnidapter API          User's Browser         Provider
   │                    │                       │                     │
   │─POST /connections──▶│                       │                     │
   │◀──authorization_url─│                       │                     │
   │                    │                       │                     │
   │──redirect to authz_url──────────────────────▶                     │
   │                    │                       │──redirect to consent──▶
   │                    │                       │◀──auth code───────────│
   │                    │◀──GET /oauth/{p}/callback?code=...&state=...──│
   │                    │──omni.oauth.complete()──────────────────────▶│
   │                    │◀──access_token + refresh_token────────────────│
   │                    │──encrypt & store credentials──▶DB             │
   │                    │──transition connection to "active"            │
   │                    │──redirect browser──────────────────────────▶│
   │                    │         {redirect_url}?connection_id=uuid     │
   ◀────────────────────────────────────────────────────────────────────
   │  user arrives back at your app; connection is now active          │
```

---

## Step 1: Configure Provider Credentials (Optional)

By default the API uses **shared fallback OAuth apps** configured via
environment variables. To use your own OAuth app (required in production):

```bash
curl -X PUT https://omnidapter.heckerlabs.ai/v1/provider-configs/google \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "123456.apps.googleusercontent.com",
    "client_secret": "GOCSPX-xxxxxxxxxxxx",
    "scopes": ["https://www.googleapis.com/auth/calendar"]
  }'
```

Register your API's OAuth callback URL with the provider:

```
https://omnidapter.heckerlabs.ai/oauth/google/callback
https://omnidapter.heckerlabs.ai/oauth/microsoft/callback
https://omnidapter.heckerlabs.ai/oauth/zoho/callback
```

---

## Step 2: Create a Connection

```bash
curl -X POST https://omnidapter.heckerlabs.ai/v1/connections \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "google",
    "external_id": "user-alice-123",
    "redirect_url": "https://yourapp.com/oauth/done"
  }'
```

Response:

```json
{
  "data": {
    "connection_id": "550e8400-...",
    "status": "pending",
    "authorization_url": "https://accounts.google.com/o/oauth2/auth?client_id=...&state=abc&code_challenge=..."
  }
}
```

---

## Step 3: Redirect the User

Redirect the user's browser to `authorization_url`. This is a direct link to
the provider's consent screen — no intermediate redirect through this API.

```js
window.location.href = data.authorization_url;
```

---

## Step 4: Handle the Callback

After the user consents (or denies), the provider redirects to the API's
callback URL. The API:

1. Validates the `state` token (anti-CSRF).
2. Exchanges the `code` for tokens via the provider's token endpoint.
3. Encrypts and stores credentials in the `connections` table.
4. Transitions the connection from `pending` → `active`.
5. Redirects the user's browser to your `redirect_url`:

**Success:**
```
https://yourapp.com/oauth/done?connection_id=550e8400-...
```

**Error (user denied / provider error):**
```
https://yourapp.com/oauth/done?error=access_denied&connection_id=550e8400-...
```

---

## Step 5: Confirm the Connection is Active

```bash
curl https://omnidapter.heckerlabs.ai/v1/connections/550e8400-... \
  -H "Authorization: Bearer $API_KEY"
```

```json
{
  "data": {
    "status": "active",
    "granted_scopes": ["https://www.googleapis.com/auth/calendar"],
    "provider_account_id": "118...34"
  }
}
```

---

## Reauthorization Flow

When a connection transitions to `needs_reauth` (token refresh has failed
`OMNIDAPTER_REAUTH_THRESHOLD` times), start a fresh OAuth flow:

```bash
curl -X POST https://omnidapter.heckerlabs.ai/v1/connections/550e8400-.../reauthorize \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"redirect_url": "https://yourapp.com/oauth/done"}'
```

The connection transitions back to `pending` and a new `authorization_url` is
returned. Follow the same flow from Step 3.

---

## PKCE (Proof Key for Code Exchange)

The omnidapter library uses **PKCE** for Google and Microsoft. The
`code_verifier` is generated server-side, encrypted with AES-256-GCM, and
stored in the `oauth_states` table. It is decrypted at callback time to
complete the token exchange. This means the API does not rely on browser
storage for PKCE security.

---

## Provider-Specific Notes

### Google Calendar

- Register redirect URI: `https://your-api-base/oauth/google/callback`
- Required scopes: `https://www.googleapis.com/auth/calendar`
- Optional offline access: `https://www.googleapis.com/auth/calendar.readonly`
- Google app must be set to "External" or published for all users

### Microsoft Outlook

- Register redirect URI in Azure AD app registration
- Required permissions: `Calendars.ReadWrite` (delegated)
- Tenant: `common` for multi-tenant apps

### Zoho Calendar

- Register redirect URI in Zoho API Console
- Required scopes: `ZohoCalendar.calendar.ALL`

### CalDAV

CalDAV uses **username/password** instead of OAuth. Pass credentials directly
when creating the connection:

```bash
curl -X POST https://omnidapter.heckerlabs.ai/v1/connections \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "caldav",
    "external_id": "user-alice-123",
    "redirect_url": "https://yourapp.com/done",
    "metadata": {
      "url": "https://caldav.example.com/",
      "username": "alice",
      "password": "secret"
    }
  }'
```

The connection transitions to `active` without a browser redirect. The `metadata`
credentials are stored encrypted.
