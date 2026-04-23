# omnidapter-sdk

Python client for the [Omnidapter](https://omnidapter.com) API.

## Installation

```bash
pip install omnidapter-sdk
```

## Usage

```python
from omnidapter_sdk import OmnidapterClient

client = OmnidapterClient(
    base_url="https://api.example.com",
    api_key="omni_live_...",
)
```

### Providers

```python
# List all available providers
providers = client.providers.list_providers()
for provider in providers.data:
    print(provider.key, provider.display_name)

# Get a specific provider
google = client.providers.get_provider(provider_key="google")
```

### Connections

```python
# List connections (optionally filter by status or provider)
connections = client.connections.list_connections(status="active", provider="google")
for conn in connections.data:
    print(conn.id, conn.provider_key, conn.status)

# Get a single connection
conn = client.connections.get_connection(connection_id="conn_...")

# Delete a connection
client.connections.delete_connection(connection_id="conn_...")
```

### Link tokens

Link tokens are short-lived tokens used to launch the Omnidapter Connect UI,
allowing an end user to authorise a new connection.

```python
from omnidapter_sdk.models import CreateLinkTokenRequest

result = client.link_tokens.create_link_token(
    create_link_token_request=CreateLinkTokenRequest(
        end_user_id="user_123",
        allowed_providers=["google", "microsoft"],
    )
)

print(result.data.token)       # lt_...
print(result.data.connect_url) # https://...?token=lt_...
print(result.data.expires_at)  # datetime
```

### Calendar

```python
from datetime import datetime, timezone

# List calendars for a connection
calendars = client.calendar.list_calendars(connection_id="conn_...")
for cal in calendars.data:
    print(cal.id, cal.name)

# List events
events = client.calendar.list_events(
    connection_id="conn_...",
    calendar_id="cal_...",
    start=datetime(2026, 4, 1, tzinfo=timezone.utc),
    end=datetime(2026, 4, 30, tzinfo=timezone.utc),
)
for event in events.data:
    print(event.id, event.title, event.start)
```

### Error handling

```python
from omnidapter_sdk.exceptions import ApiException

try:
    conn = client.connections.get_connection(connection_id="conn_unknown")
except ApiException as e:
    print(e.status)  # 404
    print(e.body)    # JSON error body
```

## Notes

- The SDK is generated from the server's OpenAPI spec via `scripts/generate_sdks.sh`.
  Run that script after pulling changes to regenerate the client code.
- Requires Python 3.10+.
