"""Hosted usage recording and free-tier enforcement."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_hosted.models.usage import HostedUsageRecord

BILLABLE_ENDPOINT_PREFIX = "calendar."


def is_billable_endpoint(endpoint: str) -> bool:
    return endpoint.startswith(BILLABLE_ENDPOINT_PREFIX)


async def count_monthly_usage(
    tenant_id: uuid.UUID,
    session: AsyncSession,
    period_start: date | None = None,
) -> int:
    if period_start is None:
        today = date.today()
        period_start = today.replace(day=1)

    start_dt = datetime(
        period_start.year, period_start.month, period_start.day, tzinfo=timezone.utc
    )
    result = await session.execute(
        select(func.count(HostedUsageRecord.id)).where(
            HostedUsageRecord.tenant_id == tenant_id,
            HostedUsageRecord.created_at >= start_dt,
            HostedUsageRecord.endpoint.like(f"{BILLABLE_ENDPOINT_PREFIX}%"),
        )
    )
    return result.scalar_one() or 0


async def record_usage(
    tenant_id: uuid.UUID,
    connection_id: uuid.UUID | None,
    endpoint: str,
    provider_key: str | None,
    response_status: int,
    duration_ms: int,
    session: AsyncSession,
) -> None:
    record = HostedUsageRecord(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        connection_id=connection_id,
        endpoint=endpoint,
        provider_key=provider_key,
        response_status=response_status,
        duration_ms=duration_ms,
        billed=False,
    )
    session.add(record)
    await session.commit()
