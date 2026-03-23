# Observability

## Request IDs

Every request gets a request ID via middleware.

- response metadata includes `meta.request_id` on most API responses
- use this ID for log correlation and support/debug workflows

## Logs

At minimum, log:

- request ID
- method + path
- response status
- error code (when present)

For OAuth callbacks, additionally log provider key and connection ID where safe.

## Suggested Metrics

- request count by endpoint/status code
- latency by endpoint (p50/p95/p99)
- auth failures (`401 invalid_api_key`)
- OAuth begin/complete failures
- connection state transition counts

## Alerting suggestions

- sustained `5xx` rate above baseline
- OAuth callback `400` spike
- elevated `401` rate
- database connectivity failures

## Tracing

If you run distributed tracing, inject request ID into trace/span attributes to align app logs and traces.
