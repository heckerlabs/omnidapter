# Examples

Quick, copy-paste API examples using `curl`.

Set once:

```bash
export OMNI_BASE_URL="http://localhost:8000"
export OMNI_API_KEY="<API_KEY>"
```

## List providers

```bash
curl -sS \
  -H "Authorization: Bearer ${OMNI_API_KEY}" \
  "${OMNI_BASE_URL}/v1/providers"
```

## Save provider OAuth credentials

```bash
curl -sS -X PUT \
  -H "Authorization: Bearer ${OMNI_API_KEY}" \
  -H "Content-Type: application/json" \
  "${OMNI_BASE_URL}/v1/provider-configs/google" \
  -d '{
    "client_id": "google-client-id",
    "client_secret": "google-client-secret",
    "scopes": ["https://www.googleapis.com/auth/calendar"]
  }'
```

## Create connection (start OAuth)

```bash
curl -sS -X POST \
  -H "Authorization: Bearer ${OMNI_API_KEY}" \
  -H "Content-Type: application/json" \
  "${OMNI_BASE_URL}/v1/connections" \
  -d '{
    "provider": "google",
    "redirect_url": "https://app.example.com/integrations/google/done"
  }'
```

The response contains:

- `data.connection_id`
- `data.authorization_url`

Redirect your user to `authorization_url`.

## List connections

```bash
curl -sS \
  -H "Authorization: Bearer ${OMNI_API_KEY}" \
  "${OMNI_BASE_URL}/v1/connections?limit=20&offset=0"
```

## List calendars for a connection

```bash
CONNECTION_ID="<connection_id>"

curl -sS \
  -H "Authorization: Bearer ${OMNI_API_KEY}" \
  "${OMNI_BASE_URL}/v1/connections/${CONNECTION_ID}/calendar/calendars"
```

## List events

```bash
curl -sS \
  -H "Authorization: Bearer ${OMNI_API_KEY}" \
  "${OMNI_BASE_URL}/v1/connections/${CONNECTION_ID}/calendar/events?calendar_id=primary"
```

## Create event

```bash
curl -sS -X POST \
  -H "Authorization: Bearer ${OMNI_API_KEY}" \
  -H "Content-Type: application/json" \
  "${OMNI_BASE_URL}/v1/connections/${CONNECTION_ID}/calendar/events" \
  -d '{
    "calendar_id": "primary",
    "summary": "Team sync",
    "start": "2026-04-01T16:00:00Z",
    "end": "2026-04-01T16:30:00Z"
  }'
```

## Reauthorize connection

```bash
curl -sS -X POST \
  -H "Authorization: Bearer ${OMNI_API_KEY}" \
  -H "Content-Type: application/json" \
  "${OMNI_BASE_URL}/v1/connections/${CONNECTION_ID}/reauthorize" \
  -d '{"redirect_url": "https://app.example.com/integrations/google/done"}'
```

## Revoke connection

```bash
curl -sS -X DELETE \
  -H "Authorization: Bearer ${OMNI_API_KEY}" \
  "${OMNI_BASE_URL}/v1/connections/${CONNECTION_ID}"
```

---

## Booking Examples

### Create a booking connection (scoped to booking service)

```bash
curl -sS -X POST \
  -H "Authorization: Bearer ${OMNI_API_KEY}" \
  -H "Content-Type: application/json" \
  "${OMNI_BASE_URL}/v1/connections" \
  -d '{
    "provider": "acuity",
    "redirect_url": "https://app.example.com/integrations/acuity/done",
    "services": ["booking"]
  }'
```

`services` scopes the OAuth authorization to booking only. Omit it to authorize
all services the provider supports.

### List bookable services

```bash
curl -sS \
  -H "Authorization: Bearer ${OMNI_API_KEY}" \
  "${OMNI_BASE_URL}/v1/connections/${CONNECTION_ID}/booking/services"
```

### Get available slots

```bash
curl -sS \
  -H "Authorization: Bearer ${OMNI_API_KEY}" \
  "${OMNI_BASE_URL}/v1/connections/${CONNECTION_ID}/booking/availability?service_id=<service_id>&start=2026-06-01T00:00:00Z&end=2026-06-07T23:59:59Z"
```

### Create a booking

```bash
curl -sS -X POST \
  -H "Authorization: Bearer ${OMNI_API_KEY}" \
  -H "Content-Type: application/json" \
  "${OMNI_BASE_URL}/v1/connections/${CONNECTION_ID}/booking/appointments" \
  -d '{
    "service_id": "<service_id>",
    "start": "2026-06-02T10:00:00Z",
    "customer": {
      "name": "Jane Doe",
      "email": "jane@example.com"
    }
  }'
```

Returns 201 with the created `Booking` object.

### Cancel a booking

```bash
curl -sS -X DELETE \
  -H "Authorization: Bearer ${OMNI_API_KEY}" \
  "${OMNI_BASE_URL}/v1/connections/${CONNECTION_ID}/booking/appointments/<appointment_id>"
```

Returns 204 on success.

### Reschedule a booking

```bash
curl -sS -X POST \
  -H "Authorization: Bearer ${OMNI_API_KEY}" \
  -H "Content-Type: application/json" \
  "${OMNI_BASE_URL}/v1/connections/${CONNECTION_ID}/booking/appointments/<appointment_id>/reschedule" \
  -d '{"new_start": "2026-06-03T14:00:00Z"}'
```

### List bookings

```bash
curl -sS \
  -H "Authorization: Bearer ${OMNI_API_KEY}" \
  "${OMNI_BASE_URL}/v1/connections/${CONNECTION_ID}/booking/appointments?start=2026-06-01T00:00:00Z&end=2026-06-30T23:59:59Z"
```

### Find a customer

```bash
curl -sS \
  -H "Authorization: Bearer ${OMNI_API_KEY}" \
  "${OMNI_BASE_URL}/v1/connections/${CONNECTION_ID}/booking/customers/search?email=jane@example.com"
```
