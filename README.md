# omnidapter

Async, connection-first, provider-agnostic integration library focused on calendar services.

## Features

- Unified calendar service interface across providers
- Provider registry + metadata introspection
- OAuth begin/complete helpers with automatic credential persistence
- Connection-level in-process token refresh locking
- Typed auth + error models
- Async iterator pagination for list operations

## Quick start

```python
omni = Omnidapter(credential_store=my_store, oauth_state_store=my_state_store)
begin = await omni.oauth.begin("google", "conn_123", "https://app/callback")
conn = await omni.connection("conn_123")
calendar = conn.calendar()
async for event in calendar.list_events("primary"):
    print(event.summary)
```
