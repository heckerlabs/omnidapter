# Migrations

`omnidapter-server` uses Alembic for schema management.

## Apply latest migrations

```bash
uv run --package omnidapter-server alembic -c apps/omnidapter-server/alembic.ini upgrade head
```

## Show current revision

```bash
uv run --package omnidapter-server alembic -c apps/omnidapter-server/alembic.ini current
```

## Create a new migration

```bash
uv run --package omnidapter-server alembic -c apps/omnidapter-server/alembic.ini revision -m "describe change"
```

If your change is autogeneratable, use `--autogenerate` and then review the output carefully.

## Rollback one revision

```bash
uv run --package omnidapter-server alembic -c apps/omnidapter-server/alembic.ini downgrade -1
```

## Production guidance

- Run backups before migration changes.
- Apply migrations before deploying application code that depends on new columns/tables.
- Prefer additive, backward-compatible migrations for zero-downtime deployments.
- Avoid destructive column/table drops in the same release as behavior changes.
