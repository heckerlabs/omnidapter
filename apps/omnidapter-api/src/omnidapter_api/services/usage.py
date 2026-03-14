"""Usage metering and free tier enforcement."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_api.models.organization import PlanType
from omnidapter_api.models.usage import UsageRecord

# Calendar endpoints that are billable
BILLABLE_ENDPOINT_PREFIX = "calendar."


def is_billable_endpoint(endpoint: str) -> bool:
    """Return True if this endpoint counts against the usage limit."""
    return endpoint.startswith(BILLABLE_ENDPOINT_PREFIX)


async def count_monthly_usage(
    org_id: uuid.UUID,
    session: AsyncSession,
    period_start: date | None = None,
) -> int:
    """Count billable API calls for the current month."""
    if period_start is None:
        today = date.today()
        period_start = today.replace(day=1)

    period_start_dt = datetime(
        period_start.year, period_start.month, period_start.day, tzinfo=timezone.utc
    )

    result = await session.execute(
        select(func.count(UsageRecord.id)).where(
            UsageRecord.organization_id == org_id,
            UsageRecord.created_at >= period_start_dt,
            UsageRecord.billed.is_(False),  # Count all, mark billable separately
        )
    )
    return result.scalar_one() or 0


async def check_free_tier(
    org_id: uuid.UUID,
    plan: str,
    session: AsyncSession,
    free_tier_calls: int,
) -> tuple[bool, int]:
    """Check if the org is over their free tier.

    Returns:
        (is_over_limit, current_usage)
    """
    if plan == PlanType.PAYG:
        return False, 0

    usage = await count_monthly_usage(org_id, session)
    return usage >= free_tier_calls, usage


async def record_usage(
    org_id: uuid.UUID,
    connection_id: uuid.UUID | None,
    endpoint: str,
    provider_key: str | None,
    response_status: int,
    duration_ms: int,
    session: AsyncSession,
) -> None:
    """Record a usage event."""
    record = UsageRecord(
        id=uuid.uuid4(),
        organization_id=org_id,
        connection_id=connection_id,
        endpoint=endpoint,
        provider_key=provider_key,
        response_status=response_status,
        duration_ms=duration_ms,
        billed=False,
    )
    session.add(record)
    await session.commit()


async def get_usage_breakdown(
    org_id: uuid.UUID,
    session: AsyncSession,
    period_start: date | None = None,
    period_end: date | None = None,
) -> dict:
    """Get usage breakdown for an organization."""
    if period_start is None:
        today = date.today()
        period_start = today.replace(day=1)
    if period_end is None:
        import calendar

        today = date.today()
        last_day = calendar.monthrange(today.year, today.month)[1]
        period_end = today.replace(day=last_day)

    start_dt = datetime(
        period_start.year, period_start.month, period_start.day, tzinfo=timezone.utc
    )
    end_dt = datetime(
        period_end.year, period_end.month, period_end.day, 23, 59, 59, tzinfo=timezone.utc
    )

    result = await session.execute(
        select(UsageRecord).where(
            UsageRecord.organization_id == org_id,
            UsageRecord.created_at >= start_dt,
            UsageRecord.created_at <= end_dt,
        )
    )
    records = result.scalars().all()

    by_provider: dict[str, int] = {}
    by_endpoint: dict[str, int] = {}
    total = len(records)

    for record in records:
        if record.provider_key:
            by_provider[record.provider_key] = by_provider.get(record.provider_key, 0) + 1
        by_endpoint[record.endpoint] = by_endpoint.get(record.endpoint, 0) + 1

    return {
        "total_calls": total,
        "by_provider": by_provider,
        "by_endpoint": by_endpoint,
    }
