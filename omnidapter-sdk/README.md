# omnidapter-sdk

Python client for the [Omnidapter](https://omnidapter.com) API.

Omnidapter lets you connect to your users' calendars (and other services) through a single unified API. You create a link token, send the user through the Connect UI to authorise their account, and then read their data using the connection that comes back.

## Installation

```bash
pip install omnidapter-sdk
```

Requires Python 3.10+.

## Getting started

Create a client with your API key and the base URL of your Omnidapter instance:

```python
from omnidapter_sdk import OmnidapterClient

client = OmnidapterClient(
    base_url="https://api.example.com",
    api_key="omni_live_...",
)
```

All methods are synchronous and return typed response objects. The actual payload is always on `.data`.

---

## Providers

Providers are the services Omnidapter can connect to (e.g. Google, Microsoft). You typically list them once to populate a picker in your UI.

```python
providers = client.providers.list_providers()
for provider in providers.data:
    print(provider.key, provider.display_name)

# Fetch a single provider by its key
google = client.providers.get_provider(provider_key="google")
print(google.data.display_name)
```

---

## Connections

A connection represents an authorised link between one of your end users and a provider. Once a user completes the Connect flow, their connection appears here.

```python
# List all connections, optionally filtering by status or provider
connections = client.connections.list_connections(status="active", provider="google")
for conn in connections.data:
    print(conn.id, conn.provider_key, conn.status)

# Fetch a single connection
conn = client.connections.get_connection(connection_id="conn_...")
print(conn.data.status)

# Revoke a connection — this also invalidates any stored credentials
client.connections.delete_connection(connection_id="conn_...")
```

---

## Link tokens

A link token is a short-lived, single-use token that grants an end user access to the Connect UI. Generate one server-side, pass it to your frontend, and redirect the user to `connect_url`. Omnidapter will handle the OAuth flow and create a connection on success.

```python
from omnidapter_sdk.models import CreateLinkTokenRequest

result = client.link_tokens.create_link_token(
    create_link_token_request=CreateLinkTokenRequest(
        end_user_id="user_123",           # your internal user ID
        allowed_providers=["google", "microsoft"],  # restrict which providers are shown
    )
)

token = result.data
print(token.token)       # lt_... — pass this to your frontend
print(token.connect_url) # redirect the user here to start the Connect flow
print(token.expires_at)  # datetime — tokens are short-lived, generate them on demand
```

---

## Calendar

Once a user has a connection, you can read their calendar data. All calendar operations require a `connection_id`.

```python
from datetime import datetime, timezone

# List the calendars available on a connection
calendars = client.calendar.list_calendars(connection_id="conn_...")
for cal in calendars.data:
    print(cal.id, cal.name)

# List events within a time range across a specific calendar
events = client.calendar.list_events(
    connection_id="conn_...",
    calendar_id="cal_...",
    start=datetime(2026, 4, 1, tzinfo=timezone.utc),
    end=datetime(2026, 4, 30, tzinfo=timezone.utc),
)
for event in events.data:
    print(event.id, event.title, event.start)
```

---

## Error handling

The SDK raises `ApiException` for any non-2xx response. You can inspect the HTTP status code and the raw response body to handle errors appropriately.

```python
from omnidapter_sdk.exceptions import ApiException

try:
    conn = client.connections.get_connection(connection_id="conn_unknown")
except ApiException as e:
    print(e.status)  # e.g. 404
    print(e.body)    # JSON error body from the server
```

---

## Notes

- The SDK is generated from the server's OpenAPI spec via `scripts/generate_sdks.sh`.
  Run that script after pulling changes to regenerate the client code.
