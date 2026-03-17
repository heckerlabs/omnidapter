# Database

The API uses **PostgreSQL ≥ 14** via SQLAlchemy 2.0 async ORM with `asyncpg`
as the driver. Schema is managed by **Alembic**.

---

## Schema Overview

```
organizations
    ├── memberships  (org_id, user_id → unique)
    ├── api_keys     (org_id → many)
    ├── provider_configs  (org_id + provider_key → unique)
    ├── connections  (org_id → many)
    │       └── oauth_states  (connection_id → many)
    └── usage_records (org_id → many, connection_id → nullable)
            └── usage_summaries (org_id + period_start → unique)
```

---

## Tables

### `organizations`

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | Auto-generated |
| `created_at` | timestamptz | |
| `updated_at` | timestamptz | Auto-updated |
| `name` | varchar(255) | Display name |
| `plan` | varchar(50) | `free` or `payg` |
| `stripe_customer_id` | varchar(255) | Nullable |
| `is_active` | boolean | Soft-delete flag |
| `settings` | jsonb | Arbitrary org settings |

---

### `users`

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | |
| `created_at` | timestamptz | |
| `updated_at` | timestamptz | |
| `name` | varchar(255) | |
| `email` | varchar(255) **unique** | |
| `workos_user_id` | varchar(255) | WorkOS SSO user ID (nullable) |

---

### `memberships`

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | |
| `created_at` | timestamptz | |
| `organization_id` | UUID FK → organizations | |
| `user_id` | UUID FK → users | |
| `role` | varchar(50) | `owner`, `admin`, or `member` |

Unique constraint: `(organization_id, user_id)`.

---

### `api_keys`

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | |
| `created_at` | timestamptz | |
| `organization_id` | UUID FK → organizations | |
| `created_by` | UUID FK → users | Nullable |
| `name` | varchar(255) | Human label (e.g., "production") |
| `key_hash` | varchar(255) **unique** | bcrypt hash of raw key |
| `key_prefix` | varchar(20) | First 12 chars for fast lookup |
| `last_used_at` | timestamptz | Nullable; updated on each auth |
| `is_active` | boolean | Revoke by setting false |

---

### `provider_configs`

Stores per-organization OAuth application credentials. Credentials are
encrypted at rest.

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | |
| `created_at` / `updated_at` | timestamptz | |
| `organization_id` | UUID FK → organizations | |
| `provider_key` | varchar(50) | e.g., `google` |
| `auth_kind` | varchar(50) | `oauth2` or `caldav` |
| `client_id_encrypted` | text | AES-256-GCM encrypted |
| `client_secret_encrypted` | text | AES-256-GCM encrypted |
| `scopes` | varchar[] | Optional scope override |
| `is_fallback` | boolean | True when using shared credentials |

Unique constraint: `(organization_id, provider_key)`.

---

### `connections`

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | |
| `created_at` / `updated_at` | timestamptz | |
| `organization_id` | UUID FK → organizations | |
| `provider_key` | varchar(50) | |
| `external_id` | varchar(255) | Your internal user/account ID (nullable) |
| `status` | varchar(50) | `pending`, `active`, `needs_reauth`, `revoked` |
| `status_reason` | text | Human-readable reason for non-active status |
| `granted_scopes` | varchar[] | Scopes granted by the user |
| `provider_account_id` | varchar(255) | Provider's user/account ID (nullable) |
| `credentials_encrypted` | text | Full token JSON, AES-256-GCM encrypted |
| `provider_config` | jsonb | Stores `redirect_url`, `metadata`, `oauth_state` |
| `refresh_failure_count` | integer | Consecutive refresh failures |
| `last_refresh_failure_at` | timestamptz | Nullable |
| `last_used_at` | timestamptz | Updated on every calendar call |

Unique constraint: `(organization_id, external_id)` (when `external_id` is set).

Indexes:
- `ix_connections_org_status` on `(organization_id, status)`
- `ix_connections_org_provider` on `(organization_id, provider_key)`

---

### `oauth_states`

Temporary records created when an OAuth flow is initiated. Deleted after
callback completion or expiry.

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | |
| `created_at` | timestamptz | |
| `expires_at` | timestamptz | State token expiry |
| `organization_id` | UUID FK → organizations | |
| `provider_key` | varchar(50) | |
| `connection_id` | UUID FK → connections | |
| `state_token` | varchar(255) **unique** | Anti-CSRF random token |
| `pkce_verifier_encrypted` | text | Encrypted PKCE code_verifier |
| `redirect_uri` | text | Callback URL sent to provider |
| `metadata` | jsonb | Arbitrary flow metadata |

Index: `ix_oauth_states_token` on `state_token`.

---

### `usage_records`

One row per API call to a calendar endpoint.

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | |
| `created_at` | timestamptz | Call timestamp |
| `organization_id` | UUID FK → organizations | |
| `connection_id` | UUID FK → connections | Nullable |
| `endpoint` | varchar(255) | e.g., `calendar.list_events` |
| `provider_key` | varchar(50) | Nullable |
| `response_status` | integer | HTTP status code |
| `duration_ms` | integer | Response time in ms |
| `billed` | boolean | Whether counted against free tier |

Index: `ix_usage_records_org_created` on `(organization_id, created_at)`.

---

### `usage_summaries`

Pre-aggregated monthly rollups (for billing integration).

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | |
| `organization_id` | UUID FK | |
| `period_start` | date | First day of billing period |
| `period_end` | date | Last day |
| `total_calls` | integer | |
| `billable_calls` | integer | |
| `total_cost_cents` | integer | |
| `stripe_invoice_id` | varchar(255) | Nullable |
| `paid_at` | timestamptz | Nullable |

Unique constraint: `(organization_id, period_start)`.

---

## Migrations

Alembic is configured in `apps/omnidapter-server/alembic.ini` and `alembic/env.py`.

### Apply migrations

```bash
cd apps/omnidapter-server
uv run alembic upgrade head
```

### Create a new migration

```bash
uv run alembic revision --autogenerate -m "add_indexes"
```

Review the generated file in `alembic/versions/` before applying.

### Roll back one migration

```bash
uv run alembic downgrade -1
```

### View migration history

```bash
uv run alembic history --verbose
```

---

## Session Management

The API uses **per-request async sessions**:

```python
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with _session_factory() as session:
        yield session
```

Sessions are injected via `Depends(get_session)`. Each request gets its own
session; commits are explicit. The session factory uses
`expire_on_commit=False` to allow attribute access after commit.

---

## Connection String Format

```
postgresql+asyncpg://user:password@host:port/database
```

For SSL in production:

```
postgresql+asyncpg://user:password@host/database?ssl=require
```
