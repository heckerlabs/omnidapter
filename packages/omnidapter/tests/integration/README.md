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

## Getting a Google refresh token

Use OAuth Playground: `https://developers.google.com/oauthplayground/`

1. Open the gear icon and enable **Use your own OAuth credentials**.
2. Paste your Google OAuth client ID/secret.
3. Select scope: `https://www.googleapis.com/auth/calendar`.
4. Click **Authorize APIs**, then complete consent.
5. Click **Exchange authorization code for tokens**.
6. Copy `refresh_token` into `OMNIDAPTER_TEST_GOOGLE_REFRESH_TOKEN`.

If no refresh token is returned, re-consent with offline access (or revoke prior consent and retry).

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
