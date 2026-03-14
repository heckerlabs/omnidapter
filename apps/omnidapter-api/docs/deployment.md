# Deployment

This guide covers deploying Omnidapter API to a production environment.

---

## Prerequisites

- PostgreSQL ≥ 14
- Python ≥ 3.10
- A 32-byte encryption key (see [Encryption](encryption.md))
- OAuth app credentials for each provider you want to support

---

## Environment Variables

Set all required environment variables before starting:

```bash
# Required
OMNIDAPTER_DATABASE_URL=postgresql+asyncpg://user:pass@db.internal:5432/omnidapter
OMNIDAPTER_ENCRYPTION_KEY=<base64-32-byte-key>
OMNIDAPTER_BASE_URL=https://api.yourdomain.com

# Provider credentials (at least one)
OMNIDAPTER_GOOGLE_CLIENT_ID=...
OMNIDAPTER_GOOGLE_CLIENT_SECRET=...
OMNIDAPTER_MICROSOFT_CLIENT_ID=...
OMNIDAPTER_MICROSOFT_CLIENT_SECRET=...

# Limits
OMNIDAPTER_FREE_TIER_CALLS=1000
OMNIDAPTER_RATE_LIMIT_FREE=60
OMNIDAPTER_RATE_LIMIT_PAID=300

# Environment
OMNIDAPTER_ENV=production
```

See [Configuration](configuration.md) for the full list.

---

## Database Setup

```bash
# Run Alembic migrations
uv run alembic upgrade head

# Bootstrap first organization and API key
uv run omnidapter-bootstrap --name "My Organization" --key-name "production"
```

---

## Starting the Server

### Directly with uvicorn

```bash
uv run uvicorn omnidapter_api.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 4 \
  --proxy-headers \
  --forwarded-allow-ips '*'
```

### Via the project script

```bash
uv run omnidapter-api
# → runs on 0.0.0.0:8000 with reload (dev mode)
```

For production, wrap with a process manager (systemd, supervisor) or use a
container.

---

## Docker

### Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install UV
RUN pip install uv

# Copy workspace files
COPY pyproject.toml uv.lock ./
COPY packages/ packages/
COPY apps/omnidapter-api/ apps/omnidapter-api/

# Install dependencies
RUN uv sync --frozen --no-dev

# Run migrations and start server
CMD ["uv", "run", "uvicorn", "omnidapter_api.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "4", "--proxy-headers"]
```

### docker-compose.yml

```yaml
version: "3.9"
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: omnidapter
      POSTGRES_USER: omnidapter
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data

  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      OMNIDAPTER_DATABASE_URL: postgresql+asyncpg://omnidapter:${DB_PASSWORD}@db:5432/omnidapter
      OMNIDAPTER_ENCRYPTION_KEY: ${OMNIDAPTER_ENCRYPTION_KEY}
      OMNIDAPTER_BASE_URL: ${OMNIDAPTER_BASE_URL}
      OMNIDAPTER_ENV: production
    depends_on:
      - db

volumes:
  pgdata:
```

---

## Reverse Proxy (nginx)

```nginx
upstream omnidapter_api {
    server 127.0.0.1:8000;
}

server {
    listen 443 ssl http2;
    server_name api.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/api.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://omnidapter_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## OAuth Callback URL Registration

Register the following callback URLs with each OAuth provider:

| Provider | Callback URL |
|---|---|
| Google | `https://api.yourdomain.com/oauth/google/callback` |
| Microsoft | `https://api.yourdomain.com/oauth/microsoft/callback` |
| Zoho | `https://api.yourdomain.com/oauth/zoho/callback` |

---

## Health Checks

```bash
curl https://api.yourdomain.com/health
# {"status": "ok"}
```

Configure your load balancer to use `GET /health` with a 2 s timeout.

---

## Security Hardening

### CORS

The default configuration allows all origins. In production, restrict to your
dashboard domain by editing `main.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://dashboard.yourdomain.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)
```

### Database connection pool

Set pool size for production workloads:

```bash
OMNIDAPTER_DATABASE_URL=postgresql+asyncpg://user:pass@db/omnidapter?pool_size=20&max_overflow=40
```

### Rate limiting

The default in-memory rate limiter works for single-process deployments. For
multi-process or multi-node deployments, replace the in-memory state with a
**Redis-backed** sliding window implementation.

### Encryption keys

Store `OMNIDAPTER_ENCRYPTION_KEY` in a secrets manager (AWS Secrets Manager,
GCP Secret Manager, HashiCorp Vault) rather than directly in environment
variables.

---

## Monitoring

### Key metrics to track

| Metric | Description |
|---|---|
| `omnidapter_api_requests_total` | Request count by endpoint and status |
| `omnidapter_api_request_duration_ms` | p50/p95/p99 latency |
| `omnidapter_connections_by_status` | Count of connections per status |
| `omnidapter_usage_calls_total` | Billable calls per org |
| `omnidapter_rate_limited_total` | 429 responses per org |

### Log fields

Every request logs:

- `request_id` — from `X-Request-ID` header
- `method` + `path`
- `status_code`
- `duration_ms`
- `org_id` (when authenticated)

---

## Scaling

The API is **stateless** except for the in-memory rate limiter. To scale
horizontally:

1. Run multiple uvicorn workers (`--workers N`) or multiple containers.
2. Replace in-memory rate limiting with Redis (see `services/rate_limit.py`).
3. Use a connection pool proxy (PgBouncer) in front of PostgreSQL.
4. Point all instances at the same PostgreSQL database.
