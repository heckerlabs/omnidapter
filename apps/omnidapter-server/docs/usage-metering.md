# Usage & Metering

The API tracks every API call and enforces a monthly free tier for
organizations on the `free` plan.

Implementation: `src/omnidapter_server/services/usage.py`

---

## Billable vs Non-Billable Endpoints

Only **calendar endpoints** count against the usage limit:

| Endpoint prefix | Billable? |
|---|---|
| `calendar.*` | Yes |
| Everything else (connections, provider-configs, usage, providers) | No |

The `is_billable_endpoint` function checks the prefix:

```python
BILLABLE_ENDPOINT_PREFIX = "calendar."

def is_billable_endpoint(endpoint: str) -> bool:
    return endpoint.startswith(BILLABLE_ENDPOINT_PREFIX)
```

### Endpoint names recorded

| Endpoint | Recorded as |
|---|---|
| List calendars | `calendar.list_calendars` |
| List events | `calendar.list_events` |
| Get event | `calendar.get_event` |
| Create event | `calendar.create_event` |
| Update event | `calendar.update_event` |
| Delete event | `calendar.delete_event` |
| Get availability | `calendar.get_availability` |

---

## Free Tier

| Plan | Monthly limit |
|---|---|
| `free` | `OMNIDAPTER_FREE_TIER_CALLS` (default: 1,000) |
| `payg` | Unlimited (billed per call) |

The limit resets at the start of each calendar month.

When a `free`-plan org exceeds the limit, the API returns **402 Payment Required**:

```json
{
  "error": {
    "code": "usage_limit_exceeded",
    "message": "Free tier limit reached. Add a payment method to continue.",
    "details": {
      "limit": 1000,
      "used": 1000
    }
  }
}
```

---

## Usage Records

Every calendar endpoint call writes a `usage_records` row **after** the
provider call completes:

```python
await record_usage(
    org_id=auth.org_id,
    connection_id=conn.id,
    endpoint="calendar.list_events",
    provider_key=conn.provider_key,
    response_status=200,
    duration_ms=142,
    session=session,
)
```

Fields recorded:

| Field | Description |
|---|---|
| `organization_id` | Authenticated org |
| `connection_id` | Connection used |
| `endpoint` | `calendar.*` string |
| `provider_key` | e.g., `google` |
| `response_status` | HTTP status returned to caller |
| `duration_ms` | Time from request to provider response |
| `billed` | `false` by default (set to `true` when invoiced via Stripe) |

Failed calls (provider errors, connection errors) are still recorded with the
appropriate `response_status` (502, 429, etc.).

---

## Usage API

```bash
# Current month
curl https://omnidapter.heckerlabs.ai/v1/usage \
  -H "Authorization: Bearer $API_KEY"

# Custom date range
curl "https://omnidapter.heckerlabs.ai/v1/usage?start=2026-01-01&end=2026-01-31" \
  -H "Authorization: Bearer $API_KEY"
```

Response:

```json
{
  "data": {
    "period_start": "2026-03-01",
    "period_end": "2026-03-31",
    "total_calls": 750,
    "free_tier_calls": 750,
    "billable_calls": 0,
    "estimated_cost_cents": 0,
    "by_provider": {
      "google": 500,
      "microsoft": 250
    },
    "by_endpoint": {
      "calendar.list_events": 400,
      "calendar.create_event": 200,
      "calendar.get_availability": 150
    }
  }
}
```

---

## Upgrading to Pay-as-You-Go

To remove the free tier limit, upgrade the organization's plan to `payg`. This
is currently done directly in the database or via a Stripe webhook handler
(not yet implemented in v0.2.0):

```sql
UPDATE organizations SET plan = 'payg' WHERE id = '...';
```

Once on `payg`, `check_free_tier()` always returns `(False, 0)` — no limit
is enforced.

---

## Usage Summaries

`usage_summaries` provides pre-aggregated monthly rollups for Stripe invoicing:

| Field | Description |
|---|---|
| `period_start` | First day of billing period |
| `period_end` | Last day |
| `total_calls` | All calls in period |
| `billable_calls` | Calls exceeding free tier |
| `total_cost_cents` | Computed cost |
| `stripe_invoice_id` | Set when Stripe invoice is created |
| `paid_at` | Set when Stripe payment succeeds |

Summaries are populated by a background billing job (not yet implemented in
v0.2.0). The `usage_records` table is the source of truth.
