# Architecture

## Overview

Omnidapter API is a **multi-tenant REST service** that sits between your
application and calendar providers (Google Calendar, Microsoft Outlook, Zoho
Calendar, CalDAV). It manages OAuth credentials on behalf of your
organization's end-users and exposes a single, unified calendar API.

```
Your App
   │
   │  Bearer omni_sk_...
   ▼
┌──────────────────────────────────────────────────────┐
│                   Omnidapter API                      │
│                                                      │
│  ┌─────────────┐   ┌──────────────┐  ┌───────────┐  │
│  │  Auth Layer  │   │ Rate Limiter │  │ Usage      │  │
│  │  (API Keys) │   │  (in-memory) │  │ Metering   │  │
│  └─────────────┘   └──────────────┘  └───────────┘  │
│                                                      │
│  ┌──────────────────────────────────────────────┐    │
│  │             FastAPI Routers                   │    │
│  │  /v1/providers  /v1/provider-configs          │    │
│  │  /v1/connections  /v1/connections/{id}/...    │    │
│  │  /oauth/{provider}/callback  /v1/usage        │    │
│  └───────────────────────┬──────────────────────┘    │
│                          │                           │
│  ┌───────────────────────▼──────────────────────┐    │
│  │            omnidapter Library                 │    │
│  │  Omnidapter(credential_store, state_store)    │    │
│  └───────────────────────┬──────────────────────┘    │
│                          │                           │
│  ┌───────────────────────▼──────────────────────┐    │
│  │           PostgreSQL (via asyncpg)            │    │
│  │  organizations  connections  usage_records    │    │
│  │  api_keys  provider_configs  oauth_states     │    │
│  └──────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────┘
         │                    │                │
   Google OAuth2     Microsoft OAuth2      Zoho / CalDAV
```

---

## Layer Breakdown

### 1. Transport / Middleware

| Component | File | Responsibility |
|---|---|---|
| `RequestIdMiddleware` | `middleware/request_id.py` | Assigns `X-Request-ID` to every request; echoed in all responses |
| `CORSMiddleware` | `main.py` | Allows cross-origin requests (tighten `allow_origins` in production) |
| Global exception handler | `main.py` | Catches unhandled exceptions and returns a safe 500 JSON body |

### 2. Authentication & Authorization

Every non-`/health` endpoint requires `Authorization: Bearer omni_sk_...`.

Flow in `dependencies.py → get_auth_context()`:

1. Parse the `Authorization` header.
2. Look up `APIKey` rows by **prefix** (first 12 chars) to limit bcrypt candidates.
3. `bcrypt.checkpw` against the stored hash.
4. Load the associated `Organization`; verify `is_active`.
5. **Rate limit check** — sliding-window in-memory counter per org.
6. Return `AuthContext(api_key, organization)` as a FastAPI dependency.

### 3. Routers

| Router | Prefix | Purpose |
|---|---|---|
| `providers` | `/v1/providers` | List registered calendar providers |
| `provider_configs` | `/v1/provider-configs` | CRUD for org-specific OAuth app credentials |
| `connections` | `/v1/connections` | Create/list/delete connections; start OAuth flows |
| `calendar` | `/v1/connections/{id}/calendar` | Proxy calendar operations to providers |
| `oauth` | `/oauth` | Handle OAuth provider callbacks (browser redirect target) |
| `usage` | `/v1/usage` | Usage breakdown for the authenticated org |

### 4. Business Logic (Services)

| Service | File | Purpose |
|---|---|---|
| `auth` | `services/auth.py` | API key generation and bcrypt verification |
| `rate_limit` | `services/rate_limit.py` | Per-org sliding-window rate limiter |
| `usage` | `services/usage.py` | Free tier check, `record_usage`, breakdown query |
| `connection_health` | `services/connection_health.py` | Refresh failure counting, status transitions |

### 5. Library Integration (Stores)

The `omnidapter` library requires two interfaces:

| Interface | Implementation | File |
|---|---|---|
| `CredentialStore` | `DatabaseCredentialStore` | `stores/credential_store.py` |
| `OAuthStateStore` | `DatabaseOAuthStateStore` | `stores/oauth_state_store.py` |

Both implementations persist to PostgreSQL and use `EncryptionService` for
sensitive fields.

An `Omnidapter` instance is constructed **per request** from the authenticated
org's provider config (or falls back to env-based fallback credentials).

### 6. Encryption

All secrets (OAuth tokens, PKCE verifiers, client secrets) are stored with
**AES-256-GCM** encryption. See [Encryption](encryption.md).

### 7. Database

PostgreSQL via `asyncpg` + SQLAlchemy 2.0 async ORM. Schema managed by Alembic.
See [Database](database.md).

---

## Request Lifecycle (Calendar Endpoint)

```
POST /v1/connections/{id}/calendar/events
     │
     ├─ RequestIdMiddleware  → assigns X-Request-ID
     │
     ├─ get_auth_context()
     │    ├─ parse Bearer token
     │    ├─ DB lookup by key prefix
     │    ├─ bcrypt verify
     │    ├─ rate limit check
     │    └─ return AuthContext
     │
     ├─ calendar router
     │    ├─ load Connection from DB (check org ownership)
     │    ├─ check_connection_status() → 409/403/410 if not active
     │    ├─ check_free_tier()         → 402 if over limit
     │    ├─ load ProviderConfig (org or fallback)
     │    ├─ build Omnidapter(cred_store, state_store)
     │    ├─ omni.calendar(connection_id).create_event(...)
     │    │       └─ library auto-refreshes token via DatabaseCredentialStore
     │    ├─ record_usage(endpoint="calendar.create_event", ...)
     │    ├─ update_last_used(connection_id)
     │    └─ return 201 JSON
     │
     └─ response with X-Request-ID + X-RateLimit-* headers
```

---

## Multi-Tenancy

Each `Organization` is fully isolated:

- All DB queries filter by `organization_id`.
- Rate limits are tracked per `org_id` in-memory.
- Provider credentials (client ID/secret) are stored per org, encrypted at rest.
- Connections, usage records, and API keys all belong to an org.

An API key authenticates to exactly one organization. There is no cross-org access.

---

## Scalability Considerations

| Concern | Current Approach | Production Path |
|---|---|---|
| Rate limiting | In-memory per process | Redis-backed sliding window |
| Session state | Per-request DB session | Already stateless — safe to scale horizontally |
| Encryption keys | Single current key + optional previous | KMS-backed key management |
| Usage metering | Real-time writes per call | Async queue + batch writes |
| OAuth state | DB rows with expiry | Already DB — works multi-process |
