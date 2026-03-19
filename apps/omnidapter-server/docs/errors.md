# Error Model

Most error responses follow:

```json
{
  "error": {
    "code": "<machine_code>",
    "message": "<human_readable_message>"
  },
  "meta": {
    "request_id": "req_..."
  }
}
```

Some FastAPI-raised detail responses can appear as:

```json
{
  "detail": {
    "code": "...",
    "message": "..."
  }
}
```

## Common Status Codes

- `400`: invalid callback input, state mismatch, provider callback error
- `401`: missing or invalid API key
- `404`: resource not found (connection/provider config)
- `410`: revoked connection operation attempted
- `422`: invalid request value (for example redirect URL)
- `500`: unexpected internal error

## Common Error Codes

- `invalid_api_key`
- `provider_not_found`
- `provider_config_not_found`
- `connection_not_found`
- `connection_revoked`
- `invalid_redirect_url`
- `fallback_connection_limit`
- `oauth_begin_failed`
- `encryption_not_configured`
- `internal_error`

## Debugging Workflow

1. Capture `meta.request_id` from the failing response.
2. Check application logs for the same request ID.
3. Verify endpoint-specific prerequisites (auth header, provider config, connection state).
4. For OAuth failures, validate callback URL, `OMNIDAPTER_BASE_URL`, and origin policy settings.
