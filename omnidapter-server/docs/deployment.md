# Deployment

## Recommended production topology

- FastAPI app behind HTTPS reverse proxy
- PostgreSQL for persistent data
- Redis for OAuth state (multi-instance safety)

## Required environment

- `OMNIDAPTER_DATABASE_URL`
- `OMNIDAPTER_ENCRYPTION_KEY`
- `OMNIDAPTER_BASE_URL`

## Hardening checklist

- Use explicit `OMNIDAPTER_ALLOWED_ORIGIN_DOMAINS` values
- Restrict network access to database and Redis
- Rotate encryption keys using current/previous key settings
- Monitor 401/422 callback errors and request IDs
