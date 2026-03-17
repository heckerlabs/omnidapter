# Getting Started

## Prerequisites

| Requirement | Version |
|---|---|
| Python | ≥ 3.10 |
| [UV](https://docs.astral.sh/uv/) | ≥ 0.4 |
| PostgreSQL | ≥ 14 |

The API lives inside the `omnidapter` UV workspace. All commands assume you
are at the **repository root** (`/path/to/omnidapter`) unless stated otherwise.

---

## 1. Install Dependencies

```bash
uv sync
```

This installs both `packages/omnidapter` (the library) and
`apps/omnidapter-server` (the hosted API) into the shared virtual environment.

---

## 2. Create a PostgreSQL Database

```bash
createdb omnidapter
```

---

## 3. Configure Environment Variables

The API reads configuration from environment variables or a `.env` file placed
in `apps/omnidapter-server/`.

**Minimum required variables:**

```bash
# apps/omnidapter-server/.env

OMNIDAPTER_DATABASE_URL=postgresql+asyncpg://localhost/omnidapter
OMNIDAPTER_ENCRYPTION_KEY=<base64-32-byte-key>
```

Generate a secure encryption key:

```bash
python -c "import os, base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

See [Configuration](configuration.md) for the full list of variables.

---

## 4. Run Database Migrations

```bash
cd apps/omnidapter-server
uv run alembic upgrade head
```

This creates all tables defined in `alembic/versions/0001_initial_schema.py`.

---

## 5. Bootstrap an Organization and API Key

```bash
uv run omnidapter-bootstrap --name "Acme Corp" --key-name "production"
```

Output:

```
Organization created: 550e8400-e29b-41d4-a716-446655440000
API Key (shown once): omni_sk_AbCdEfGhIjKlMnOpQrStUvWxYz012345
Key prefix: omni_sk_AbCd
```

> **Important:** Copy the full API key — it is shown only once. The server only
> stores a bcrypt hash.

---

## 6. Start the Server

```bash
# From repository root
uv run omnidapter-server
```

Or from the app directory:

```bash
cd apps/omnidapter-server
uv run uvicorn omnidapter_server.main:app --reload --host 0.0.0.0 --port 8000
```

The server starts on `http://localhost:8000`.

| URL | Description |
|---|---|
| `http://localhost:8000/health` | Health check |
| `http://localhost:8000/docs` | Swagger UI (interactive) |
| `http://localhost:8000/redoc` | ReDoc |

---

## 7. Make Your First Request

```bash
export API_KEY="omni_sk_AbCdEfGhIjKlMnOpQrStUvWxYz012345"

# List available providers
curl http://localhost:8000/v1/providers \
  -H "Authorization: Bearer $API_KEY"
```

Response:

```json
{
  "data": [
    {"key": "google", "name": "Google Calendar", "auth_kind": "oauth2"},
    {"key": "microsoft", "name": "Microsoft Outlook", "auth_kind": "oauth2"},
    {"key": "zoho", "name": "Zoho Calendar", "auth_kind": "oauth2"},
    {"key": "caldav", "name": "CalDAV", "auth_kind": "caldav"}
  ]
}
```

---

## 8. Create a Connection (OAuth Flow)

```bash
curl -X POST http://localhost:8000/v1/connections \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "google",
    "redirect_url": "https://yourapp.com/oauth/callback",
    "external_id": "user-123"
  }'
```

Response:

```json
{
  "connection_id": "a1b2c3d4-...",
  "status": "pending",
  "authorization_url": "https://accounts.google.com/o/oauth2/auth?..."
}
```

Redirect your user to `authorization_url`. After they authorize, Google
redirects to `https://omnidapter.heckerlabs.ai/oauth/google/callback?code=...`,
the API completes the flow and then redirects the user's browser to:

```
https://yourapp.com/oauth/callback?connection_id=a1b2c3d4-...
```

The connection is now `active` and ready to use.

---

## 9. List Calendars

```bash
curl http://localhost:8000/v1/connections/a1b2c3d4-.../calendar/calendars \
  -H "Authorization: Bearer $API_KEY"
```

---

## Next Steps

- [API Reference](api-reference.md) — full endpoint documentation
- [OAuth Flows](oauth.md) — how to configure provider credentials
- [Configuration](configuration.md) — all environment variables
- [Testing](testing.md) — running tests
