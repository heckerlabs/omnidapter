# Self-Hosting

This page covers practical self-hosting guidance for `omnidapter-server`.

## What self-hosted means here

- You run the API in your own infrastructure.
- Your API keys are global admin keys for your deployment.
- You manage database, secrets, backups, and network perimeter.

## Minimum production stack

- `omnidapter-server` app
- PostgreSQL
- Redis (recommended for OAuth state in multi-instance deployments)
- HTTPS reverse proxy (Nginx, Caddy, Traefik, etc.)

## Critical environment variables

- `OMNIDAPTER_DATABASE_URL`
- `OMNIDAPTER_ENCRYPTION_KEY` (required in production)
- `OMNIDAPTER_BASE_URL`
- `OMNIDAPTER_ALLOWED_ORIGIN_DOMAINS`

Optional but recommended:

- `OMNIDAPTER_OAUTH_STATE_REDIS_URL`
- provider fallback OAuth credentials (`OMNIDAPTER_GOOGLE_*`, etc.)

## Recommended deployment checklist

1. Run migrations before first boot.
2. Bootstrap an initial API key with `omnidapter-bootstrap`.
3. Set explicit allowed origin domains for production.
4. Terminate TLS at your proxy and force HTTPS.
5. Restrict DB/Redis network access to app nodes.
6. Back up PostgreSQL and test restore procedures.
7. Monitor 4xx/5xx rates and request IDs.

## Scaling notes

- Horizontal scaling is safe when OAuth state is shared (Redis/DB).
- In-memory OAuth state is development-only and can break callbacks across instances.
- Keep app instances stateless and rely on shared persistence.

## Security notes

- API keys are powerful in self-hosted mode. Protect and rotate them.
- Keep encryption keys in a secret manager; never commit them.
- Use short network paths between proxy and app.
