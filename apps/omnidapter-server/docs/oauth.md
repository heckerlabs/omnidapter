# OAuth Flow

`POST /v1/connections` starts OAuth and returns an authorization URL.

## Step 1: Begin

Client calls `POST /v1/connections` with provider and redirect URL.

Server:

1. Creates a pending connection
2. Builds provider registry
3. Starts OAuth via `omni.oauth.begin(...)`
4. Stores OAuth state metadata on the connection

## Step 2: Provider callback

Provider redirects to:

`GET /oauth/{provider_key}/callback?code=...&state=...`

Server:

1. Loads OAuth state
2. Resolves connection
3. Exchanges code for tokens (`omni.oauth.complete(...)`)
4. Persists credentials
5. Marks connection active
6. Redirects user to originally requested redirect URL

## Reauthorization

`POST /v1/connections/{connection_id}/reauthorize` repeats OAuth flow for an existing connection.

The server requests the union of existing granted scopes and provider-config scopes.

## Security checks

- callback `state` must exist and match
- redirect URLs are origin-policy validated
- provider credentials are encrypted at rest
