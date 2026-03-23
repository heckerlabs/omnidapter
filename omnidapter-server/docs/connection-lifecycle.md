# Connection Lifecycle

Connections move through these states:

- `pending`: OAuth flow started, credentials not finalized
- `active`: valid credentials available
- `needs_reauth`: refresh failures reached threshold
- `revoked`: deleted or permanently invalidated

## Transitions

- `POST /v1/connections` -> `pending`
- successful OAuth callback -> `active`
- repeated refresh failures -> `needs_reauth`
- `POST /v1/connections/{id}/reauthorize` -> `pending` -> `active`
- `DELETE /v1/connections/{id}` -> `revoked`

## Notes

- Revoked connections are terminal and cannot be reauthorized.
- Reauthorization preserves previously granted scopes by requesting scope union.
