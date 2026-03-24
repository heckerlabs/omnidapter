# Omnidapter

Provider-agnostic calendar integrations for Python and self-hosted APIs.

Omnidapter is open source (MIT-licensed).

If you are tired of writing one integration for Google, another for Microsoft,
then patching edge cases forever, Omnidapter gives you one consistent model and
one API surface.

## Why Use Omnidapter

- One unified calendar interface across major providers
- Built-in OAuth lifecycle management (begin, callback completion, refresh)
- Clean separation of credential storage from provider logic
- Self-hosted REST API available when you do not want SDK coupling
- Strong test coverage and explicit capability checks for provider differences

## Choose Your Path

- I want a Python SDK: start with `omnidapter-core/README.md`
- I want a self-hosted API: start with `omnidapter-server/docs/README.md`

## What You Get In This Repository

- `omnidapter-core` - `omnidapter` Python library
- `omnidapter-server` - self-hosted FastAPI service that wraps core

```text
omnidapter-core/
omnidapter-server/
omnidapter-hosted/
```

## 60-Second Quick Start (Library)

```bash
pip install omnidapter
```

```python
from omnidapter import Omnidapter

omni = Omnidapter(
    credential_store=my_credential_store,
    oauth_state_store=my_oauth_state_store,
)

conn = await omni.connection("conn_123")
cal = conn.calendar()

calendars = await cal.list_calendars()
```

Core docs:

- `omnidapter-core/README.md`
- `omnidapter-core/docs/providers.md`
- `omnidapter-core/docs/calendar.md`
- `omnidapter-core/docs/credential-stores.md`

## 60-Second Quick Start (Self-Hosted API)

```bash
uv sync
uv run --package omnidapter-server alembic -c omnidapter-server/alembic.ini upgrade head
uv run omnidapter-bootstrap --name "local"
uv run omnidapter-server
```

Docker Compose file locations:

- `omnidapter-server/docker-compose.yml` (self-hosted server)
- `omnidapter-hosted/docker-compose.yml` (hosted multi-tenant app)

Then call it:

```bash
curl -H "Authorization: Bearer <API_KEY>" \
  http://localhost:8000/v1/providers
```

Server docs:

- `omnidapter-server/docs/README.md`

## How It Stays Simple

- Core handles provider-specific transport and mapping
- You own credentials and OAuth state persistence strategy
- Server wraps the same core flows with consistent JSON contracts
- Capability checks make unsupported provider operations explicit

## Development

```bash
uv run poe --help
uv run poe check
```

`uv run poe check` runs format, lint, typecheck, tests, and package builds.

Useful task shortcuts:

- `uv run poe server-up`
- `uv run poe server-bootstrap`
- `uv run poe hosted-up`

## License

MIT
