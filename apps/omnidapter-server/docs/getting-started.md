# Getting Started

## Prerequisites

- Python 3.10+
- `uv`
- PostgreSQL

## 1) Install dependencies

From repository root:

```bash
uv sync
```

## 2) Configure environment

At minimum set:

- `OMNIDAPTER_DATABASE_URL`
- `OMNIDAPTER_ENCRYPTION_KEY` (optional only if `OMNIDAPTER_ENV=LOCAL`)
- `OMNIDAPTER_BASE_URL`

See [Configuration](configuration.md) for all settings.

## 3) Run migrations

```bash
uv run --package omnidapter-server alembic -c apps/omnidapter-server/alembic.ini upgrade head
```

## 4) Bootstrap first API key

```bash
uv run omnidapter-bootstrap --name "Default" --key-name "local"
```

## 5) Start server

```bash
uv run omnidapter-server
```

Optional Docker Compose path:

```bash
cp apps/omnidapter-server/.env.example apps/omnidapter-server/.env
docker compose -f apps/omnidapter-server/docker-compose.yml up -d --build
```

Server endpoints:

- `http://localhost:8000/health`
- `http://localhost:8000/docs`
- `http://localhost:8000/redoc`

## 6) First authenticated request

```bash
curl -H "Authorization: Bearer <API_KEY>" \
  http://localhost:8000/v1/providers
```

Next steps:

- [Examples](examples.md)
- [OAuth Flow](oauth.md)
- [Self-Hosting](self-hosting.md)
