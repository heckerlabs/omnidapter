# Omnidapter API — Documentation

Omnidapter API (v0.2.0) is a managed REST service that wraps the
[`omnidapter`](../../packages/omnidapter) Python library, providing a hosted
calendar-integration platform with multi-tenant organizations, OAuth management,
encrypted credential storage, usage metering, and per-organization rate limiting.

## Contents

| Document | Description |
|---|---|
| [Getting Started](getting-started.md) | Installation, local setup, and first request |
| [Architecture](architecture.md) | System design, layers, data flow |
| [Configuration](configuration.md) | All environment variables and their defaults |
| [Authentication](authentication.md) | API key format, Bearer token usage, rate limits |
| [API Reference](api-reference.md) | Every endpoint — path, method, request body, responses |
| [OAuth Flows](oauth.md) | How OAuth per-provider is initiated and completed |
| [Connection Lifecycle](connection-lifecycle.md) | State machine: pending → active → needs_reauth → revoked |
| [Database](database.md) | Schema overview, models, running Alembic migrations |
| [Encryption](encryption.md) | AES-256-GCM at rest, key rotation |
| [Usage & Metering](usage-metering.md) | Free tier enforcement, billable calls, usage records |
| [Testing](testing.md) | Running unit and integration tests |
| [Deployment](deployment.md) | Production deployment guide |

## Quick Start

```bash
# 1. Install dependencies (UV workspace)
uv sync

# 2. Set required environment variables
export OMNIDAPTER_DATABASE_URL="postgresql+asyncpg://user:pass@localhost/omnidapter"
export OMNIDAPTER_ENCRYPTION_KEY="<base64-encoded-32-byte-key>"

# 3. Run Alembic migrations
cd apps/omnidapter-api
uv run alembic upgrade head

# 4. Bootstrap first org and API key
uv run omnidapter-bootstrap --name "My Org" --key-name "production"

# 5. Start the server
uv run omnidapter-api
# → http://localhost:8000
# → http://localhost:8000/docs  (Swagger UI)
# → http://localhost:8000/redoc (ReDoc)
```

## Project Layout

```
apps/omnidapter-api/
├── alembic/                   # Database migrations
│   └── versions/
│       └── 0001_initial_schema.py
├── docs/                      # This documentation
├── src/omnidapter_api/
│   ├── config.py              # Pydantic settings (env vars)
│   ├── database.py            # SQLAlchemy async engine + session
│   ├── dependencies.py        # FastAPI Depends helpers (auth, encryption)
│   ├── encryption.py          # AES-256-GCM encrypt/decrypt
│   ├── errors.py              # Library exception → HTTP mapping
│   ├── main.py                # FastAPI app, middleware, routers
│   ├── middleware/
│   │   └── request_id.py      # X-Request-ID header middleware
│   ├── models/                # SQLAlchemy ORM models
│   ├── routers/               # FastAPI route handlers
│   ├── schemas/               # Pydantic request/response schemas
│   ├── scripts/
│   │   └── bootstrap.py       # CLI: create org + API key
│   ├── services/              # Business logic (auth, rate limit, usage, health)
│   └── stores/                # CredentialStore + OAuthStateStore impls
└── tests/
    ├── unit/                  # Pure unit tests (no DB required)
    └── integration/           # Integration tests (require Postgres)
```
