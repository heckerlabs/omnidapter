# Configuration

Settings are environment-driven (`OMNIDAPTER_*`) plus runtime bind vars (`HOST`, `PORT`).

## Required

- `OMNIDAPTER_DATABASE_URL`
- `OMNIDAPTER_ENCRYPTION_KEY` (required in `DEV` and `PROD`; optional in `LOCAL`)
- `OMNIDAPTER_BASE_URL`

## Database

- `OMNIDAPTER_DATABASE_URL` (default `postgresql+asyncpg://localhost/omnidapter`)

## Encryption

- `OMNIDAPTER_ENCRYPTION_KEY` (optional only when `OMNIDAPTER_ENV=LOCAL`)
- `OMNIDAPTER_ENCRYPTION_KEY_PREVIOUS` (optional key rotation support)

## OAuth State Store

- Redis (`OMNIDAPTER_OAUTH_STATE_REDIS_URL`) is preferred
- In-memory is used when Redis URL is unset (warning logged)
- In-memory is not suitable for multi-worker deployments

## Fallback Provider OAuth Credentials

- `OMNIDAPTER_GOOGLE_CLIENT_ID`
- `OMNIDAPTER_GOOGLE_CLIENT_SECRET`
- `OMNIDAPTER_MICROSOFT_CLIENT_ID`
- `OMNIDAPTER_MICROSOFT_CLIENT_SECRET`
- `OMNIDAPTER_ZOHO_CLIENT_ID`
- `OMNIDAPTER_ZOHO_CLIENT_SECRET`

## Runtime Behavior

- `HOST` (default `0.0.0.0`)
- `PORT` (default `8000`)
- `OMNIDAPTER_FALLBACK_CONNECTION_LIMIT` (default `5`)
- `OMNIDAPTER_REAUTH_THRESHOLD` (default `3`)
- `OMNIDAPTER_ENV` (default `DEV`; values: `DEV`, `LOCAL`, `PROD`)
- `OMNIDAPTER_ALLOWED_ORIGIN_DOMAINS` (default `*`)

## CORS and Redirect Domains

`OMNIDAPTER_ALLOWED_ORIGIN_DOMAINS` controls:

- CORS allow-list behavior
- redirect URL validation for OAuth callbacks

Use explicit domains in production whenever possible.
