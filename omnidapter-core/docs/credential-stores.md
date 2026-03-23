# Credential Stores

Omnidapter Core expects caller-owned persistence for credentials and OAuth state.

## Required Interfaces

- `CredentialStore`
  - `get_credentials(connection_id)`
  - `save_credentials(connection_id, credentials)`
  - `delete_credentials(connection_id)`
- `OAuthStateStore`
  - `save_state(state_id, payload, expires_at)`
  - `load_state(state_id)`
  - `delete_state(state_id)`

## Production Guidance

- Do not use in-memory stores in production.
- Encrypt tokens at rest.
- Use shared OAuth state storage for multi-instance deployments.

## Typical Stack

- Credentials: relational DB table with encrypted payloads
- OAuth state: Redis with TTL

## `connection_id`

`connection_id` is caller-defined and opaque to Omnidapter.
Use a UUID or your own stable identifier and keep your own user mapping.
