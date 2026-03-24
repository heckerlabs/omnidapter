# Authentication

All `/v1/*` endpoints require an API key via Bearer token.

## Header format

```http
Authorization: Bearer <API_KEY>
```

## Failure modes

- Missing header -> `401 invalid_api_key`
- Non-Bearer scheme -> `401 invalid_api_key`
- Invalid/inactive key -> `401 invalid_api_key`

## Request IDs

Every response includes request metadata with `request_id`.
Use this ID for troubleshooting and log correlation.

## Key lifecycle

Use `omnidapter-bootstrap` initially to create a key:

```bash
uv run omnidapter-bootstrap --name "local"
```

Bootstrap inserts a row in `api_keys` with key name/prefix/hash and prints the
raw key once. Store that raw key securely; it is not retrievable later.

Key last-used timestamps are updated on authenticated requests.
