# Usage Metering

`omnidapter-server` is self-hosted and does not ship hosted billing enforcement.

If you need usage-based billing in your environment:

- measure request volume per API key and endpoint
- aggregate usage in your own billing pipeline
- enforce quotas/rate limits at proxy, API gateway, or custom middleware

## Suggested billable dimensions

- calendar reads (`GET .../events`, `GET .../calendars`)
- calendar writes (`POST/PATCH/DELETE .../events`)
- connection lifecycle calls (`POST /connections`, reauthorize)

## Implementation notes

- keep metering decoupled from provider business logic
- store request IDs with metered events for auditability
- validate expected event volume with periodic reconciliation
