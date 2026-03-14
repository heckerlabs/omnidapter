# Authentication

## API Keys

Every request to a protected endpoint must include an API key in the
`Authorization` header:

```http
Authorization: Bearer omni_sk_AbCdEfGhIjKlMnOpQrStUvWxYz012345
```

### Key Format

```
omni_sk_<32 random alphanumeric characters>
```

- **Prefix:** `omni_sk_` (8 chars)
- **Random part:** 32 chars from `[A-Za-z0-9]` (secrets.choice)
- **Total length:** 40 chars
- **Key prefix stored:** first 12 chars (e.g. `omni_sk_AbCd`) for fast DB lookup

### Key Storage

API keys are **never stored in plaintext**. The server stores:

| Field | Value |
|---|---|
| `key_hash` | `bcrypt(raw_key)` — used for verification |
| `key_prefix` | First 12 chars — used to reduce bcrypt candidates on lookup |

When authenticating, the server:

1. Extracts the key prefix from the incoming key.
2. Queries for all active `APIKey` rows with that prefix (typically just one).
3. Runs `bcrypt.checkpw(incoming_key, stored_hash)` for each candidate.
4. Loads the associated `Organization`; checks `is_active`.

### Creating an API Key

**Via CLI (bootstrap script):**

```bash
uv run omnidapter-bootstrap --name "My Org" --key-name "production"
```

Output:
```
Organization created: 550e8400-...
API Key (shown once): omni_sk_AbCdEfGhIjKlMnOpQrStUvWxYz012345
Key prefix: omni_sk_AbCd
```

> The raw key is displayed **exactly once**. It cannot be recovered after this point.

**Via API (not yet implemented — use bootstrap script for now).**

---

## Rate Limiting

Rate limits are enforced per organization using an **in-memory sliding window**
over a 60-second period.

### Limits by Plan

| Plan | Requests per 60 s | Default |
|---|---|---|
| `free` | `OMNIDAPTER_RATE_LIMIT_FREE` | 60 |
| `payg` | `OMNIDAPTER_RATE_LIMIT_PAID` | 300 |

### Response Headers

Every authenticated response includes:

```http
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 59
X-RateLimit-Reset: 1741911600
```

- `X-RateLimit-Limit` — total requests allowed in the window
- `X-RateLimit-Remaining` — requests remaining until window resets
- `X-RateLimit-Reset` — Unix timestamp when the window resets

### Rate Limit Exceeded

When the limit is exceeded the API returns **429 Too Many Requests**:

```json
{
  "error": {
    "code": "rate_limited",
    "message": "Rate limit exceeded"
  },
  "meta": {"request_id": "req_abc123"}
}
```

With headers:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 42
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1741911600
```

---

## Error Responses

### Missing Authorization Header

```http
HTTP/1.1 401 Unauthorized
```

```json
{
  "error": {
    "code": "invalid_api_key",
    "message": "Missing Authorization header"
  }
}
```

### Invalid Authorization Format

```http
HTTP/1.1 401 Unauthorized
```

```json
{
  "error": {
    "code": "invalid_api_key",
    "message": "Authorization header must be 'Bearer <key>'"
  }
}
```

### Invalid or Inactive Key

```http
HTTP/1.1 401 Unauthorized
```

```json
{
  "error": {
    "code": "invalid_api_key",
    "message": "Invalid or inactive API key"
  }
}
```

---

## Request IDs

Every response includes an `X-Request-ID` header and a `meta.request_id` field
in the response body. If the caller supplies an `X-Request-ID` header, that
value is echoed back; otherwise a new `req_<uuid>` is generated.

```http
X-Request-ID: req_01HZABCDE...
```

```json
{
  "data": {...},
  "meta": {"request_id": "req_01HZABCDE..."}
}
```

Use the request ID when reporting issues or correlating logs.
