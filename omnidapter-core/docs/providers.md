# Provider Setup

This guide covers built-in provider setup for Omnidapter Core.

---

## Calendar Providers

### Google

- Auth: OAuth 2.0 + PKCE
- Env vars: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
- Typical scopes: `https://www.googleapis.com/auth/calendar`

### Microsoft (Calendar)

- Auth: OAuth 2.0 + PKCE
- Env vars: `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`
- Typical scopes: `Calendars.ReadWrite`, `offline_access`
- Microsoft also supports `ServiceKind.BOOKING` — see Microsoft Bookings below.

### Zoho

- Auth: OAuth 2.0
- Env vars: `ZOHO_CLIENT_ID`, `ZOHO_CLIENT_SECRET`

### Apple

- Auth: Basic (app-specific password)
- No OAuth callback flow
- Enable: `OMNIDAPTER_APPLE_ENABLED=1`

### CalDAV

- Auth: Basic
- Not auto-registered by default
- Enable: `OMNIDAPTER_CALDAV_ENABLED=1`, or register manually with `CalDAVProvider()`

---

## Booking Providers

### Acuity Scheduling

- Auth: OAuth 2.0 (no PKCE)
- Env vars: `ACUITY_CLIENT_ID`, `ACUITY_CLIENT_SECRET`
- Scopes: `api-v1` (single scope, covers all Acuity operations)
- Rate limit: 10 req/s
- Note: "calendars" in the Acuity API are staff members — `list_staff()` maps to `GET /calendars`

### Cal.com

- Auth: OAuth 2.0 + PKCE
- Env vars: `CALCOM_CLIENT_ID`, `CALCOM_CLIENT_SECRET`
- All requests include `cal-api-version: 2024-08-13` header automatically
- Supports `MULTI_SERVICE` and `MULTI_LOCATION`

### Square Appointments

- Auth: OAuth 2.0 + PKCE
- Env vars: `SQUARE_CLIENT_ID`, `SQUARE_CLIENT_SECRET`
- Scopes: `APPOINTMENTS_READ`, `APPOINTMENTS_WRITE`
- Note: `create_booking` fetches `service_variation_version` from Catalog API automatically; idempotency key generated per request

### Calendly

- Auth: OAuth 2.0 (no PKCE)
- Env vars: `CALENDLY_CLIENT_ID`, `CALENDLY_CLIENT_SECRET`
- Read-only: `CREATE_BOOKING`, `RESCHEDULE_BOOKING`, and `CUSTOMER_MANAGEMENT` are not supported
- Booking `management_urls` are populated from Calendly's hosted cancel/reschedule links

### Microsoft Bookings

- Auth: OAuth 2.0 + PKCE (same app registration as Microsoft Calendar)
- Env vars: `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`
- Additional scope: `Bookings.ReadWrite.All` — requested automatically when `services=["booking"]`
- Requires `business_id` (the booking business email address) in the connection's `provider_config`:
  ```python
  stored_credential.provider_config = {"business_id": "mybusiness@example.com"}
  ```
- Availability via `POST .../getStaffAvailability` (Graph API)

---

## OAuth Flow Pattern

```python
# Begin OAuth — request specific services
result = await omni.oauth.begin(
    provider="acuity",
    connection_id="<id>",
    redirect_uri="https://yourapp.com/oauth/acuity/callback",
    requested_services=[ServiceKind.BOOKING],  # optional — scopes authorization to booking only
)
# Redirect user to result.authorization_url

# Complete OAuth after callback
await omni.oauth.complete(
    provider="acuity",
    connection_id="<id>",
    code=request.query["code"],
    state=request.query["state"],
    redirect_uri="https://yourapp.com/oauth/acuity/callback",
)
# StoredCredential.granted_services is set to [ServiceKind.BOOKING]
```

When `requested_services` is provided, `OAuthHelper.begin()` builds the scope
set by unioning scope groups where `service_kind is None` (always included) with
scope groups matching the requested services. This allows a single provider
(e.g. Microsoft) to have calendar and booking authorized independently.

## Auto Registration

With `auto_register_by_env=True` (default), OAuth providers are registered only
when the corresponding env vars are present. Apple and CalDAV require their
respective enable flags.
