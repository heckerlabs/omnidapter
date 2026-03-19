# Configuration

All settings are environment-driven (`OMNIDAPTER_*`).

## Required

- `OMNIDAPTER_DATABASE_URL`
- `OMNIDAPTER_ENCRYPTION_KEY`
- `OMNIDAPTER_BASE_URL`

## Database

- `OMNIDAPTER_DATABASE_URL` (default `postgresql+asyncpg://localhost/omnidapter`)

## Encryption

- `OMNIDAPTER_ENCRYPTION_KEY`
- `OMNIDAPTER_ENCRYPTION_KEY_PREVIOUS` (optional key rotation support)

## OAuth State Store

Priority order:

1. Redis (`OMNIDAPTER_OAUTH_STATE_REDIS_URL`)
2. DB (`OMNIDAPTER_OAUTH_STATE_DB_URL`)
3. In-memory fallback (development only)

## Fallback Provider OAuth Credentials

- `OMNIDAPTER_GOOGLE_CLIENT_ID`
- `OMNIDAPTER_GOOGLE_CLIENT_SECRET`
- `OMNIDAPTER_MICROSOFT_CLIENT_ID`
- `OMNIDAPTER_MICROSOFT_CLIENT_SECRET`
- `OMNIDAPTER_ZOHO_CLIENT_ID`
- `OMNIDAPTER_ZOHO_CLIENT_SECRET`

## Runtime Behavior

- `OMNIDAPTER_FALLBACK_CONNECTION_LIMIT` (default `5`)
- `OMNIDAPTER_REAUTH_THRESHOLD` (default `3`)
- `OMNIDAPTER_ENV` (default `development`)
- `OMNIDAPTER_ALLOWED_ORIGIN_DOMAINS` (default `*`)

## CORS and Redirect Domains

`OMNIDAPTER_ALLOWED_ORIGIN_DOMAINS` controls:

- CORS allow-list behavior
- redirect URL validation for OAuth callbacks

Use explicit domains in production whenever possible.
