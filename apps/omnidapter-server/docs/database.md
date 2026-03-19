# Database

`omnidapter-server` uses SQLAlchemy + Alembic with PostgreSQL.

## Primary tables

- `api_keys`
- `connections`
- `provider_configs`
- `oauth_states`

## Migrations

```bash
uv run --package omnidapter-server alembic -c apps/omnidapter-server/alembic.ini upgrade head
```

## Connection storage

- Connection metadata and state are stored in `connections`.
- Credentials are encrypted before persistence.
- OAuth temporary state is persisted in configured state store backend.
