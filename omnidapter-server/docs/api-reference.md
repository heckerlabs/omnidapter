# API Reference

Base URL: `http://<host>:8000`

Authentication: all `/v1/*` endpoints require `Authorization: Bearer <API_KEY>`.

For interactive schemas, use:

- Swagger: `/docs`
- ReDoc: `/redoc`

## Health

- `GET /health`

## Providers

- `GET /v1/providers`
- `GET /v1/providers/{provider_key}`

## Provider Configs

- `GET /v1/provider-configs`
- `GET /v1/provider-configs/{provider_key}`
- `PUT /v1/provider-configs/{provider_key}`
- `DELETE /v1/provider-configs/{provider_key}`

Provider configs store encrypted OAuth client credentials for each provider.

## Connections

- `POST /v1/connections`
- `GET /v1/connections`
- `GET /v1/connections/{connection_id}`
- `DELETE /v1/connections/{connection_id}`
- `POST /v1/connections/{connection_id}/reauthorize`

## Calendar Proxy

- `GET /v1/connections/{connection_id}/calendar/calendars`
- `GET /v1/connections/{connection_id}/calendar/events`
- `GET /v1/connections/{connection_id}/calendar/events/{event_id}`
- `POST /v1/connections/{connection_id}/calendar/events`
- `PATCH /v1/connections/{connection_id}/calendar/events/{event_id}`
- `DELETE /v1/connections/{connection_id}/calendar/events/{event_id}`
- `GET /v1/connections/{connection_id}/calendar/availability`

## Booking Proxy

All booking endpoints are under `/v1/connections/{connection_id}/booking/`.
The connection must have been authorized for `ServiceKind.BOOKING` — pass
`"services": ["booking"]` in the connection creation request.

### Services & Staff
- `GET /v1/connections/{connection_id}/booking/services`
- `GET /v1/connections/{connection_id}/booking/services/{service_id}`
- `GET /v1/connections/{connection_id}/booking/staff`
- `GET /v1/connections/{connection_id}/booking/staff/{staff_id}`
- `GET /v1/connections/{connection_id}/booking/locations`

### Availability
- `GET /v1/connections/{connection_id}/booking/availability?service_id=&start=&end=`

### Appointments
- `GET /v1/connections/{connection_id}/booking/appointments`
- `POST /v1/connections/{connection_id}/booking/appointments` → 201
- `GET /v1/connections/{connection_id}/booking/appointments/{appointment_id}`
- `PATCH /v1/connections/{connection_id}/booking/appointments/{appointment_id}`
- `DELETE /v1/connections/{connection_id}/booking/appointments/{appointment_id}` → 204
- `POST /v1/connections/{connection_id}/booking/appointments/{appointment_id}/reschedule`

### Customers
- `GET /v1/connections/{connection_id}/booking/customers/search?email=`
- `GET /v1/connections/{connection_id}/booking/customers/{customer_id}`
- `POST /v1/connections/{connection_id}/booking/customers` → 201

## OAuth Callback

- `GET /oauth/{provider_key}/callback`

This endpoint is used by providers after user consent.

## Response Shape

Most endpoints return:

```json
{
  "data": {},
  "meta": { "request_id": "req_..." }
}
```

Errors return:

```json
{
  "error": {
    "code": "...",
    "message": "..."
  },
  "meta": { "request_id": "req_..." }
}
```

See also:

- [Examples](examples.md)
- [Error Model](errors.md)
