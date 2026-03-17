# Integration Tests

These tests run against real provider accounts and are skipped by default.

## 1) Prepare environment

From repo root, sync dependencies:

```bash
uv sync --all-packages
```

Create your env file from the template:

```bash
cp packages/omnidapter/tests/integration/.env.example packages/omnidapter/tests/integration/.env
```

Fill in credentials/tokens in `packages/omnidapter/tests/integration/.env`.

## 2) Run tests with env file

All integration tests:

```bash
uv run --env-file packages/omnidapter/tests/integration/.env pytest packages/omnidapter/tests/integration
```

Google only:

```bash
uv run --env-file packages/omnidapter/tests/integration/.env pytest packages/omnidapter/tests/integration/test_google.py
```

Microsoft only:

```bash
uv run --env-file packages/omnidapter/tests/integration/.env pytest packages/omnidapter/tests/integration/test_microsoft.py
```

Zoho only:

```bash
uv run --env-file packages/omnidapter/tests/integration/.env pytest packages/omnidapter/tests/integration/test_zoho.py
```

CalDAV only:

```bash
uv run --env-file packages/omnidapter/tests/integration/.env pytest packages/omnidapter/tests/integration/test_caldav.py
```

Apple only:

```bash
uv run --env-file packages/omnidapter/tests/integration/.env pytest packages/omnidapter/tests/integration/test_apple.py
```

## Required env vars by provider

- Common: `OMNIDAPTER_INTEGRATION=1`
  - Optional: `OMNIDAPTER_TEST_ATTENDEE_EMAIL` (comma-separated list for attendee invite tests)
- Google:
  - `OMNIDAPTER_TEST_GOOGLE_CLIENT_ID`
  - `OMNIDAPTER_TEST_GOOGLE_CLIENT_SECRET`
  - `OMNIDAPTER_TEST_GOOGLE_REFRESH_TOKEN`
  - Optional: `OMNIDAPTER_TEST_GOOGLE_CALENDAR_ID`
- Microsoft:
  - `OMNIDAPTER_TEST_MICROSOFT_CLIENT_ID`
  - `OMNIDAPTER_TEST_MICROSOFT_CLIENT_SECRET`
  - `OMNIDAPTER_TEST_MICROSOFT_REFRESH_TOKEN`
  - Optional: `OMNIDAPTER_TEST_MICROSOFT_CALENDAR_ID`
- Zoho:
  - `OMNIDAPTER_TEST_ZOHO_CLIENT_ID`
  - `OMNIDAPTER_TEST_ZOHO_CLIENT_SECRET`
  - `OMNIDAPTER_TEST_ZOHO_REFRESH_TOKEN`
  - Optional: `OMNIDAPTER_TEST_ZOHO_CALENDAR_ID`
- CalDAV:
  - `OMNIDAPTER_TEST_CALDAV_URL`
  - `OMNIDAPTER_TEST_CALDAV_USERNAME`
  - `OMNIDAPTER_TEST_CALDAV_PASSWORD`
  - Optional: `OMNIDAPTER_TEST_CALDAV_CALENDAR_ID`
- Apple:
  - `OMNIDAPTER_TEST_APPLE_USERNAME`
  - `OMNIDAPTER_TEST_APPLE_PASSWORD`
  - Optional: `OMNIDAPTER_TEST_APPLE_CALENDAR_ID`

## Notes

- Use dedicated test accounts/calendars where possible.
- Tests create/update/delete events and clean up after themselves.
- If a provider's required env vars are missing, that provider's integration tests are skipped.
- CalDAV `test_calendar_crud_round_trip` may skip when the configured CalDAV server blocks `MKCALENDAR` (for example, Zoho CalDAV sync endpoints). Use iCloud or a self-hosted CalDAV server that allows calendar collection creation for full CalDAV calendar CRUD coverage.

## Getting a Google refresh token

Use OAuth Playground: `https://developers.google.com/oauthplayground/`

1. Open the gear icon and enable **Use your own OAuth credentials**.
2. Paste your Google OAuth client ID/secret.
3. Select scope: `https://www.googleapis.com/auth/calendar`.
4. Click **Authorize APIs**, then complete consent.
5. Click **Exchange authorization code for tokens**.
6. Copy `refresh_token` into `OMNIDAPTER_TEST_GOOGLE_REFRESH_TOKEN`.

If no refresh token is returned, re-consent with offline access (or revoke prior consent and retry).

## Getting Microsoft client id/secret and refresh token

1. Create an app registration in Azure Portal:
   - `https://portal.azure.com/` -> **Microsoft Entra ID** -> **App registrations** -> **New registration**
   - Supported account type: use both org + personal accounts if you want to test with Outlook/Hotmail, or single tenant if org-only
2. Add a Web redirect URI under **Authentication**:
   - `http://localhost:8000/oauth/microsoft/callback`
3. Create client credentials:
   - **Certificates & secrets** -> **New client secret**
   - Copy **Application (client) ID** and secret **Value**
4. Ensure delegated Microsoft Graph scopes include:
   - `Calendars.ReadWrite`
   - `offline_access`
   - `openid`
   - `email`
5. If portal save fails with `api.requestedAccessTokenVersion` when enabling personal accounts, update app **Manifest**:

```json
"signInAudience": "AzureADandPersonalMicrosoftAccount",
"api": {
  "requestedAccessTokenVersion": 2
}
```

6. Open authorize URL in browser (replace `client_id` if needed):

```text
https://login.microsoftonline.com/common/oauth2/v2.0/authorize?client_id=<your-client-id>&response_type=code&redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Foauth%2Fmicrosoft%2Fcallback&response_mode=query&scope=offline_access%20Calendars.ReadWrite%20openid%20email&prompt=consent
```

7. After consent, copy the `code` query param from the callback URL.
8. Exchange the code for tokens:

```bash
curl -X POST "https://login.microsoftonline.com/common/oauth2/v2.0/token" \
  --data-urlencode "client_id=<your-client-id>" \
  --data-urlencode "client_secret=<your-client-secret>" \
  --data-urlencode "grant_type=authorization_code" \
  --data-urlencode "code=<auth-code-from-callback>" \
  --data-urlencode "redirect_uri=http://localhost:8000/oauth/microsoft/callback" \
  --data-urlencode "scope=offline_access Calendars.ReadWrite openid email"
```

9. Copy `refresh_token` into `OMNIDAPTER_TEST_MICROSOFT_REFRESH_TOKEN`.

Notes:
- If your app is org-only, replace `common` with your tenant ID in both authorize/token endpoints.
- `code` is short-lived and single-use; exchange immediately.
- `redirect_uri` must match exactly in Azure config, authorize request, and token request (including `localhost` vs `127.0.0.1`).

## Getting a Zoho refresh token

1. Create a Server-based OAuth client in Zoho API Console:
   - `https://api-console.zoho.com/`
2. Add your redirect URI (for local app flow used here):
   - `http://127.0.0.1:8000/oauth/zoho/callback`
3. Open the authorize URL in browser (replace `client_id`):

```text
https://accounts.zoho.com/oauth/v2/auth?response_type=code&client_id=<your-client-id>&scope=ZohoCalendar.calendar.ALL,ZohoCalendar.event.ALL&redirect_uri=http%3A%2F%2F127.0.0.1%3A8000%2Foauth%2Fzoho%2Fcallback&access_type=offline&prompt=consent
```

4. After consent, copy the `code` from the callback URL.
5. Exchange the code for tokens:

```bash
curl -X POST "https://accounts.zoho.com/oauth/v2/token" \
  --data-urlencode "client_id=<your-client-id>" \
  --data-urlencode "client_secret=<your-client-secret>" \
  --data-urlencode "grant_type=authorization_code" \
  --data-urlencode "redirect_uri=http://127.0.0.1:8000/oauth/zoho/callback" \
  --data-urlencode "code=<auth-code-from-callback>"
```

6. Copy `refresh_token` into `OMNIDAPTER_TEST_ZOHO_REFRESH_TOKEN`.

Notes:
- The `code` is single-use and short-lived; exchange it immediately.
- `redirect_uri` must exactly match both the authorize request and Zoho app config.
- If your account is not on US DC, use your region host (for example `accounts.zoho.eu`).

## Getting Apple credentials (iCloud CalDAV)

Apple integration tests use Basic auth with your Apple ID email plus an app-specific password.

1. Go to `https://appleid.apple.com/` and sign in.
2. Under **Sign-In and Security**, enable two-factor authentication if it is not already enabled.
3. In **App-Specific Passwords**, generate a new password.
4. Use these env vars:
   - `OMNIDAPTER_TEST_APPLE_USERNAME=<your-apple-id-email>`
   - `OMNIDAPTER_TEST_APPLE_PASSWORD=<app-specific-password>`
5. For CalDAV tests against iCloud, set:
   - `OMNIDAPTER_TEST_CALDAV_URL=https://caldav.icloud.com`
   - `OMNIDAPTER_TEST_CALDAV_USERNAME=<same-apple-id-email>`
   - `OMNIDAPTER_TEST_CALDAV_PASSWORD=<same-app-specific-password>`

Notes:
- Use the app-specific password, not your regular Apple ID password.
- If auth fails, generate a fresh app-specific password and retry.
