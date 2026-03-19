# Operations

## Migrations

Apply:

```bash
uv run --package omnidapter-server alembic -c apps/omnidapter-server/alembic.ini upgrade head
```

Detailed guidance: [Migrations](migrations.md)

## Quality checks

From repo root:

```bash
uv run ruff check .
uv run pyright
uv run pytest
```

## Build artifacts

```bash
uv build
```

Run in `apps/omnidapter-server` or via workspace tooling.

## Deployment basics

- Set production `OMNIDAPTER_*` env vars
- Use managed Postgres
- Use Redis for OAuth state in multi-instance setups
- Put service behind HTTPS reverse proxy

See also: [Self-Hosting](self-hosting.md), [Deployment](deployment.md)

## Common troubleshooting

- `401 invalid_api_key`: verify Bearer header and active key
- OAuth callback failures: check `OMNIDAPTER_BASE_URL` and redirect origins
- Missing tokens after callback: verify shared OAuth state store
- Encryption errors: verify current/previous encryption key configuration

For response formats and error code references, see [Error Model](errors.md).
