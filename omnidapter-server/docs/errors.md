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

- `400`: invalid request — bad input, unknown provider, missing fields, credential validation failure
- `401`: missing or invalid API key
- `403`: authorization failure — missing OAuth scopes or service not authorized on this connection
- `404`: resource not found (connection/provider config)
- `409`: conflict — booking slot taken between availability check and creation
- `410`: revoked connection operation attempted
- `422`: Pydantic model validation failure, or customer resolution failure during booking
- `500`: unexpected internal error

## Common Error Codes

- `invalid_api_key`
- `provider_not_found`
- `provider_config_not_found`
- `connection_not_found`
- `connection_revoked`
- `invalid_redirect_url`
- `oauth_begin_failed`
- `encryption_not_configured`
- `internal_error`

## Booking Error Codes

- `invalid_service_kind` (400) — unknown value in `services` during connection creation
- `scope_insufficient` (403) — connection lacks required OAuth scopes; response includes `required_scopes` and `granted_scopes`
- `service_not_authorized` (403) — connection was not authorized for this service kind; response includes `required_services` and `granted_services`
- `slot_unavailable` (409) — booking slot was taken between `GET /availability` and `POST /appointments`
- `customer_resolution_failed` (422) — find-or-create customer failed during booking creation

## Debugging Workflow

1. Capture `meta.request_id` from the failing response.
2. Check application logs for the same request ID.
3. Verify endpoint-specific prerequisites (auth header, provider config, connection state).
4. For OAuth failures, validate callback URL, `OMNIDAPTER_BASE_URL`, and origin policy settings.
