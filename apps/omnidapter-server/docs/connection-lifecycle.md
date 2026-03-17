# Connection Lifecycle

A connection represents a single end-user's authorization to a calendar
provider. It moves through a defined state machine.

---

## States

| Status | Description |
|---|---|
| `pending` | Created, OAuth flow started but not completed |
| `active` | OAuth completed, credentials valid, ready to use |
| `needs_reauth` | Token refresh has failed too many times; user must re-authorize |
| `revoked` | Connection has been deleted or explicitly revoked |

---

## State Machine

```
                    ┌────────┐
                    │        │
 POST /connections  │        ▼
 ──────────────────▶ pending
                    │        │
                    │        │ OAuth callback success
                    │        │ (transition_to_active)
                    │        ▼
                    │  ┌──────────┐
                    │  │          │◀─────────────────────┐
                    │  │  active  │                      │
                    │  │          │ token refresh failure │
                    │  └──────────┘ (count < threshold)  │
                    │        │                           │
                    │        │ failure count ≥ threshold  │
                    │        │ (record_refresh_failure)   │
                    │        ▼                           │
                    │  ┌─────────────┐                   │
                    │  │             │  reauthorize       │
                    │  │needs_reauth │──────────────────▶ pending
                    │  │             │
                    │  └─────────────┘
                    │        │
                    │        │ DELETE /connections/{id}
                    │        │ or OAuth callback error
                    │        ▼
                    │  ┌─────────┐
                    └─▶│ revoked │
                       └─────────┘
```

---

## Transitions

### `pending → active`

Triggered automatically when the OAuth callback completes successfully
(`GET /oauth/{provider}/callback`).

```python
await transition_to_active(
    connection_id=conn_id,
    session=session,
    granted_scopes=stored_credential.granted_scopes,
    provider_account_id=stored_credential.provider_account_id,
)
```

Sets `refresh_failure_count = 0`, `status_reason = None`.

---

### `active → needs_reauth`

Triggered when the omnidapter library fails to refresh the OAuth token and
the failure count reaches `OMNIDAPTER_REAUTH_THRESHOLD` (default: 3).

```python
await record_refresh_failure(
    connection_id=conn_id,
    session=session,
    reauth_threshold=settings.omnidapter_reauth_threshold,
)
```

Sets:
- `refresh_failure_count += 1`
- `last_refresh_failure_at = now()`
- `status = "needs_reauth"` (when count >= threshold)
- `status_reason = "Token refresh failed repeatedly. Please reauthorize."`

---

### `active/needs_reauth → revoked`

Triggered by `DELETE /v1/connections/{id}` or on OAuth callback failure.

```python
await transition_to_revoked(conn_id, session, reason="Deleted by organization")
```

---

### `needs_reauth → pending`

Triggered by `POST /v1/connections/{id}/reauthorize`. Restarts the OAuth flow.
On completion, transitions back to `active`.

---

### `active → active` (refresh success)

After a successful token refresh, the library calls the credential store's
`save()`, which internally calls:

```python
await record_refresh_success(connection_id, session)
```

Resets `refresh_failure_count = 0` and `last_refresh_failure_at = None`.

---

## Checking Status in Your App

Before displaying calendar data, check if the connection needs attention:

| Status | What to show the user |
|---|---|
| `pending` | "Please complete the OAuth flow to connect your calendar." |
| `active` | Ready — show calendar data normally |
| `needs_reauth` | "Your calendar connection needs to be re-authorized. Click here to reconnect." |
| `revoked` | "Your calendar connection was removed." |

The API returns `403 connection_needs_reauth`, `409 connection_pending`, or
`410 connection_revoked` on calendar endpoint calls for non-active connections.

---

## `last_used_at`

Every successful calendar endpoint call updates `connections.last_used_at`.
Use this field to detect stale connections that may indicate the user no longer
needs the integration.

---

## Implementation Details

State transitions are implemented in `src/omnidapter_server/services/connection_health.py`.

All transitions use SQLAlchemy `update()` statements and `await session.commit()`
— they are atomic within a single database transaction.
