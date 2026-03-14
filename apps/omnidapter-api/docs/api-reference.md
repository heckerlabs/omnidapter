# API Reference

All endpoints are under `https://omnidapter.heckerlabs.ai` (or your
self-hosted base URL). Every protected endpoint requires:

```http
Authorization: Bearer omni_sk_...
```

Responses always include a `meta.request_id` field and an `X-Request-ID`
response header.

---

## Health

### `GET /health`

No authentication required.

**Response 200**

```json
{"status": "ok"}
```

---

## Providers

### `GET /v1/providers`

List all registered calendar providers.

**Response 200**

```json
{
  "data": [
    {
      "provider_key": "google",
      "display_name": "Google Calendar",
      "services": ["calendar"],
      "auth_kinds": ["oauth2"],
      "capabilities": ["create_event", "update_event", "delete_event", "get_availability"],
      "connection_config_fields": []
    },
    {
      "provider_key": "microsoft",
      "display_name": "Microsoft Outlook",
      "services": ["calendar"],
      "auth_kinds": ["oauth2"],
      "capabilities": ["create_event", "update_event", "delete_event", "get_availability"],
      "connection_config_fields": []
    },
    {
      "provider_key": "zoho",
      "display_name": "Zoho Calendar",
      "services": ["calendar"],
      "auth_kinds": ["oauth2"],
      "capabilities": ["create_event", "update_event", "delete_event"],
      "connection_config_fields": []
    },
    {
      "provider_key": "caldav",
      "display_name": "CalDAV",
      "services": ["calendar"],
      "auth_kinds": ["caldav"],
      "capabilities": ["create_event", "update_event", "delete_event"],
      "connection_config_fields": [
        {"name": "url", "description": "CalDAV server URL", "required": true},
        {"name": "username", "description": "Username", "required": true},
        {"name": "password", "description": "Password", "required": true}
      ]
    }
  ],
  "meta": {"request_id": "req_abc123"}
}
```

---

### `GET /v1/providers/{provider_key}`

Get details for a single provider.

**Path parameters**

| Parameter | Description |
|---|---|
| `provider_key` | Provider identifier: `google`, `microsoft`, `zoho`, `caldav` |

**Response 200** — same shape as a single element from the list above.

**Response 404**

```json
{
  "error": {"code": "provider_not_found", "message": "Provider 'xyz' not found"},
  "meta": {"request_id": "req_abc123"}
}
```

---

## Provider Configs

Manage per-organization OAuth application credentials. When set, these
override the shared fallback credentials for that provider.

### `GET /v1/provider-configs`

List all provider configs for the authenticated organization.

**Response 200**

```json
{
  "data": [
    {
      "id": "uuid",
      "provider_key": "google",
      "auth_kind": "oauth2",
      "scopes": ["https://www.googleapis.com/auth/calendar"],
      "is_fallback": false,
      "created_at": "2026-03-14T10:00:00Z",
      "updated_at": "2026-03-14T10:00:00Z"
    }
  ],
  "meta": {"request_id": "req_abc123"}
}
```

---

### `GET /v1/provider-configs/{provider_key}`

Get the provider config for a specific provider.

**Response 404** when no custom config exists.

---

### `PUT /v1/provider-configs/{provider_key}`

Create or replace the provider config for a provider.
`client_id` and `client_secret` are stored encrypted at rest.

**Request body**

```json
{
  "client_id": "123456.apps.googleusercontent.com",
  "client_secret": "GOCSPX-xxxxxxxxxxxx",
  "scopes": ["https://www.googleapis.com/auth/calendar"]
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `client_id` | string | Yes | OAuth app client ID |
| `client_secret` | string | Yes | OAuth app client secret |
| `scopes` | string[] | No | Override default scopes |

**Response 200** — `ProviderConfigResponse` (client_id/secret are never returned).

---

### `DELETE /v1/provider-configs/{provider_key}`

Delete the provider config. Connections created after deletion will revert to
shared fallback credentials.

**Response 204** — no body.

**Response 404** when no config exists.

---

## Connections

### `POST /v1/connections`

Create a connection and begin the OAuth flow.

**Request body**

```json
{
  "provider": "google",
  "external_id": "user-123",
  "redirect_url": "https://yourapp.com/oauth/done",
  "metadata": {"user_email": "alice@example.com"}
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `provider` | string | Yes | Provider key: `google`, `microsoft`, `zoho`, `caldav` |
| `external_id` | string | No | Your internal identifier for the end-user. Must be unique per org+provider. |
| `redirect_url` | string | Yes | URL to redirect the user after OAuth completes (success or failure) |
| `metadata` | object | No | Arbitrary key-value data stored with the connection |

**Response 201**

```json
{
  "data": {
    "connection_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "pending",
    "authorization_url": "https://accounts.google.com/o/oauth2/auth?client_id=...&state=..."
  },
  "meta": {"request_id": "req_abc123"}
}
```

Redirect your user to `authorization_url`. After the user completes the OAuth
flow, the API redirects them to:

```
https://yourapp.com/oauth/done?connection_id=550e8400-...
```

**Response 422** — provider not supported, or fallback connection limit reached.

---

### `GET /v1/connections`

List connections for the authenticated organization.

**Query parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `status` | string | — | Filter by status: `pending`, `active`, `needs_reauth`, `revoked` |
| `provider` | string | — | Filter by provider key |
| `limit` | integer | 50 | Max results (1–200) |
| `offset` | integer | 0 | Pagination offset |

**Response 200**

```json
{
  "data": [
    {
      "id": "uuid",
      "provider": "google",
      "external_id": "user-123",
      "status": "active",
      "status_reason": null,
      "granted_scopes": ["https://www.googleapis.com/auth/calendar"],
      "provider_account_id": "118...34",
      "created_at": "2026-03-14T10:00:00Z",
      "last_used_at": "2026-03-14T11:30:00Z"
    }
  ],
  "meta": {
    "request_id": "req_abc123",
    "pagination": {
      "total": 42,
      "limit": 50,
      "offset": 0,
      "has_more": false
    }
  }
}
```

---

### `GET /v1/connections/{connection_id}`

Get a single connection.

**Response 200** — single `ConnectionResponse` in `data`.

**Response 404** — connection not found or belongs to another org.

---

### `DELETE /v1/connections/{connection_id}`

Revoke and delete a connection. Transitions status to `revoked`.

**Response 204** — no body.

**Response 404** — connection not found.

---

### `POST /v1/connections/{connection_id}/reauthorize`

Restart the OAuth flow for an existing connection. Use this when a connection
transitions to `needs_reauth`.

**Request body**

```json
{
  "redirect_url": "https://yourapp.com/oauth/done"
}
```

**Response 200**

```json
{
  "data": {
    "connection_id": "uuid",
    "status": "pending",
    "authorization_url": "https://accounts.google.com/o/oauth2/auth?..."
  },
  "meta": {"request_id": "req_abc123"}
}
```

**Response 410** — connection is revoked; create a new one instead.

---

## Calendar Endpoints

All calendar endpoints require an **active** connection. They record usage and
enforce free-tier limits.

Common errors across all calendar endpoints:

| HTTP | Code | Description |
|---|---|---|
| 402 | `usage_limit_exceeded` | Free tier monthly limit reached |
| 403 | `connection_needs_reauth` | Connection needs reauthorization |
| 404 | `connection_not_found` | Connection not found |
| 409 | `connection_pending` | OAuth not completed yet |
| 410 | `connection_revoked` | Connection has been revoked |
| 422 | `unsupported_capability` | Provider doesn't support this operation |
| 429 | `provider_rate_limited` | Calendar provider returned 429 |
| 502 | `provider_error` | Calendar provider returned an error |
| 502 | `provider_unavailable` | Network or transport error reaching provider |

---

### `GET /v1/connections/{connection_id}/calendar/calendars`

List all calendars accessible via this connection.

**Response 200**

```json
{
  "data": [
    {
      "id": "primary",
      "name": "Alice Smith",
      "description": null,
      "timezone": "America/New_York",
      "is_primary": true,
      "can_edit": true
    }
  ],
  "meta": {"request_id": "req_abc123"}
}
```

---

### `GET /v1/connections/{connection_id}/calendar/events`

List events in a calendar.

**Query parameters**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `calendar_id` | string | Yes | Calendar ID from `list_calendars` |
| `start` | ISO 8601 datetime | No | Earliest event start (inclusive) |
| `end` | ISO 8601 datetime | No | Latest event end (exclusive) |
| `page_size` | integer | No | Max events to return |

**Response 200**

```json
{
  "data": [
    {
      "id": "evt_abc123",
      "calendar_id": "primary",
      "title": "Team Standup",
      "description": "Daily sync",
      "start": "2026-03-14T09:00:00-05:00",
      "end": "2026-03-14T09:30:00-05:00",
      "timezone": "America/New_York",
      "all_day": false,
      "attendees": [
        {"email": "alice@example.com", "name": "Alice", "status": "accepted"}
      ],
      "location": null,
      "html_link": "https://calendar.google.com/...",
      "recurrence": null
    }
  ],
  "meta": {"request_id": "req_abc123"}
}
```

---

### `GET /v1/connections/{connection_id}/calendar/events/{event_id}`

Get a single event by ID.

**Query parameters**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `calendar_id` | string | Yes | Calendar the event belongs to |

**Response 200** — single event object in `data`.

---

### `POST /v1/connections/{connection_id}/calendar/events`

Create a new calendar event.

**Request body** (`CreateEventRequest` from omnidapter library)

```json
{
  "calendar_id": "primary",
  "title": "Product Review",
  "start": "2026-03-20T14:00:00-05:00",
  "end": "2026-03-20T15:00:00-05:00",
  "description": "Q1 product review",
  "attendees": [
    {"email": "bob@example.com", "name": "Bob"}
  ],
  "location": "Conf Room A",
  "timezone": "America/New_York"
}
```

**Response 201** — created event object in `data`.

---

### `PATCH /v1/connections/{connection_id}/calendar/events/{event_id}`

Update an existing event.

**Request body** (`UpdateEventRequest` from omnidapter library) — all fields optional

```json
{
  "calendar_id": "primary",
  "title": "Updated Title",
  "start": "2026-03-20T15:00:00-05:00",
  "end": "2026-03-20T16:00:00-05:00"
}
```

**Response 200** — updated event object in `data`.

---

### `DELETE /v1/connections/{connection_id}/calendar/events/{event_id}`

Delete an event.

**Query parameters**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `calendar_id` | string | Yes | Calendar the event belongs to |

**Response 204** — no body.

---

### `GET /v1/connections/{connection_id}/calendar/availability`

Get free/busy availability windows.

**Query parameters**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `calendar_id` | string | Yes | Calendar to check |
| `start` | ISO 8601 datetime | Yes | Start of availability window |
| `end` | ISO 8601 datetime | Yes | End of availability window |

**Response 200**

```json
{
  "data": {
    "busy_slots": [
      {
        "start": "2026-03-20T09:00:00-05:00",
        "end": "2026-03-20T09:30:00-05:00"
      }
    ],
    "time_min": "2026-03-20T08:00:00-05:00",
    "time_max": "2026-03-20T17:00:00-05:00"
  },
  "meta": {"request_id": "req_abc123"}
}
```

---

## Usage

### `GET /v1/usage`

Get API usage breakdown for the authenticated organization.

**Query parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `start` | ISO 8601 date | First day of current month | Period start (inclusive) |
| `end` | ISO 8601 date | Last day of current month | Period end (inclusive) |

**Response 200**

```json
{
  "data": {
    "period_start": "2026-03-01",
    "period_end": "2026-03-31",
    "total_calls": 450,
    "free_tier_calls": 450,
    "billable_calls": 0,
    "estimated_cost_cents": 0,
    "by_provider": {
      "google": 300,
      "microsoft": 150
    },
    "by_endpoint": {
      "calendar.list_events": 250,
      "calendar.create_event": 100,
      "calendar.get_availability": 100
    }
  },
  "meta": {"request_id": "req_abc123"}
}
```

---

## OAuth Callback (Internal)

### `GET /oauth/{provider_key}/callback`

This endpoint is called by the OAuth provider's redirect URI. **Do not call
this endpoint directly from your application.** The user's browser is
redirected here automatically after they complete the OAuth consent screen.

On success, the browser is redirected to the `redirect_url` supplied when
creating the connection:

```
{redirect_url}?connection_id={uuid}
```

On failure, the browser is redirected to:

```
{redirect_url}?error={provider_error}&connection_id={uuid}
```

---

## Error Response Format

All errors follow this envelope:

```json
{
  "error": {
    "code": "snake_case_code",
    "message": "Human-readable description",
    "details": {}
  },
  "meta": {
    "request_id": "req_abc123"
  }
}
```

### Error Codes

| Code | HTTP | Description |
|---|---|---|
| `invalid_api_key` | 401 | Missing, malformed, or inactive API key |
| `rate_limited` | 429 | API rate limit exceeded |
| `connection_not_found` | 404 | Connection not found |
| `connection_pending` | 409 | OAuth flow not completed |
| `connection_needs_reauth` | 403 | Token refresh failed; reauthorize needed |
| `connection_revoked` | 410 | Connection has been revoked |
| `usage_limit_exceeded` | 402 | Free tier monthly limit reached |
| `provider_not_found` | 404 | Provider key not registered |
| `provider_config_not_found` | 404 | No custom config for this provider |
| `fallback_connection_limit` | 422 | Too many connections with shared credentials |
| `provider_rate_limited` | 429 | Calendar provider returned 429 |
| `provider_error` | 502 | Calendar provider API error |
| `provider_unavailable` | 502 | Network error reaching provider |
| `scope_insufficient` | 403 | Granted scopes don't cover this operation |
| `unsupported_capability` | 422 | Provider doesn't support this operation |
| `auth_error` | 401 | Authentication error with provider |
| `internal_error` | 500 | Unexpected server error |
