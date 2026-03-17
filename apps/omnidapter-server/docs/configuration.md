# Configuration

All configuration is read from **environment variables** or a `.env` file
placed at `apps/omnidapter-server/.env`. Variable names are case-insensitive.

Settings are defined in `src/omnidapter_server/config.py` as a Pydantic
`BaseSettings` class.

---

## Database

| Variable | Default | Description |
|---|---|---|
| `OMNIDAPTER_DATABASE_URL` | `postgresql+asyncpg://localhost/omnidapter` | PostgreSQL connection string. Must use the `asyncpg` driver. |

**Example:**
```bash
OMNIDAPTER_DATABASE_URL=postgresql+asyncpg://omniadapter:secret@db.example.com:5432/omniadapter
```

---

## Encryption

| Variable | Default | Description |
|---|---|---|
| `OMNIDAPTER_ENCRYPTION_KEY` | _(empty — required)_ | Base64-encoded 32-byte AES key. Used to encrypt credentials at rest. |
| `OMNIDAPTER_ENCRYPTION_KEY_PREVIOUS` | `""` | Previous encryption key for key rotation. Allows decrypting values encrypted before a key rotation. |

Generate a key:
```bash
python -c "import os, base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

See [Encryption](encryption.md) for the full key rotation process.

---

## Fallback OAuth App Credentials

When an organization has not configured their own OAuth app, the API falls back
to these shared credentials. Set at least one provider pair for OAuth to work
out of the box.

| Variable | Default | Description |
|---|---|---|
| `OMNIDAPTER_GOOGLE_CLIENT_ID` | `""` | Google OAuth app client ID |
| `OMNIDAPTER_GOOGLE_CLIENT_SECRET` | `""` | Google OAuth app client secret |
| `OMNIDAPTER_MICROSOFT_CLIENT_ID` | `""` | Microsoft Azure app client ID |
| `OMNIDAPTER_MICROSOFT_CLIENT_SECRET` | `""` | Microsoft Azure app client secret |
| `OMNIDAPTER_ZOHO_CLIENT_ID` | `""` | Zoho OAuth app client ID |
| `OMNIDAPTER_ZOHO_CLIENT_SECRET` | `""` | Zoho OAuth app client secret |

---

## Limits

| Variable | Default | Description |
|---|---|---|
| `OMNIDAPTER_FALLBACK_CONNECTION_LIMIT` | `5` | Max connections per org when using fallback (shared) OAuth credentials |
| `OMNIDAPTER_FREE_TIER_CALLS` | `1000` | Monthly billable API calls included for free-plan orgs |
| `OMNIDAPTER_REAUTH_THRESHOLD` | `3` | Number of consecutive token refresh failures before a connection transitions to `needs_reauth` |
| `OMNIDAPTER_RATE_LIMIT_FREE` | `60` | Max requests per 60 seconds for free-plan orgs |
| `OMNIDAPTER_RATE_LIMIT_PAID` | `300` | Max requests per 60 seconds for pay-as-you-go orgs |

---

## Billing (Stripe)

| Variable | Default | Description |
|---|---|---|
| `STRIPE_SECRET_KEY` | `""` | Stripe secret key for subscription management |
| `STRIPE_WEBHOOK_SECRET` | `""` | Stripe webhook signing secret for event verification |

---

## Auth (WorkOS)

| Variable | Default | Description |
|---|---|---|
| `WORKOS_CLIENT_ID` | `""` | WorkOS client ID (reserved for future dashboard auth) |
| `WORKOS_API_KEY` | `""` | WorkOS API key (reserved for future dashboard auth) |

---

## Application

| Variable | Default | Description |
|---|---|---|
| `OMNIDAPTER_BASE_URL` | `https://omnidapter.heckerlabs.ai` | Public base URL of this API. Used to construct OAuth callback URLs sent to providers. |
| `OMNIDAPTER_ENV` | `development` | Environment name. Set to `production` to disable debug modes. |

---

## Example `.env` File

```bash
# apps/omnidapter-server/.env

# Database
OMNIDAPTER_DATABASE_URL=postgresql+asyncpg://localhost/omnidapter

# Encryption (generate with: python -c "import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())")
OMNIDAPTER_ENCRYPTION_KEY=dGhpcyBpcyBhIHRlc3Qga2V5IGZvciBkZXZlbG9wbWVudA==

# Google OAuth app (fallback)
OMNIDAPTER_GOOGLE_CLIENT_ID=123456789.apps.googleusercontent.com
OMNIDAPTER_GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxx

# Microsoft Azure app (fallback)
OMNIDAPTER_MICROSOFT_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
OMNIDAPTER_MICROSOFT_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxx

# Limits
OMNIDAPTER_FREE_TIER_CALLS=1000
OMNIDAPTER_RATE_LIMIT_FREE=60
OMNIDAPTER_RATE_LIMIT_PAID=300

# App
OMNIDAPTER_BASE_URL=https://omnidapter.heckerlabs.ai
OMNIDAPTER_ENV=production
```

---

## Settings Precedence

1. Actual environment variables (highest priority)
2. `.env` file in `apps/omnidapter-server/`
3. Pydantic `BaseSettings` defaults (lowest priority)
