"""Usage schemas."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class UsageResponse(BaseModel):
    period_start: date
    period_end: date
    total_calls: int
    free_tier_calls: int
    billable_calls: int
    estimated_cost_cents: int
    by_provider: dict[str, int]
    by_endpoint: dict[str, int]
