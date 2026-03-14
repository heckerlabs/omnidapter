"""Usage reporting endpoint."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_api.config import Settings, get_settings
from omnidapter_api.database import get_session
from omnidapter_api.dependencies import AuthContext, get_auth_context, get_request_id
from omnidapter_api.schemas.usage import UsageResponse
from omnidapter_api.services.usage import get_usage_breakdown

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("")
async def get_usage(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
    start: date | None = Query(None),
    end: date | None = Query(None),
):
    breakdown = await get_usage_breakdown(
        org_id=auth.org_id,
        session=session,
        period_start=start,
        period_end=end,
    )

    today = date.today()
    period_start = start or today.replace(day=1)
    if end is None:
        import calendar as cal

        last_day = cal.monthrange(today.year, today.month)[1]
        period_end = today.replace(day=last_day)
    else:
        period_end = end

    total_calls = breakdown["total_calls"]
    free_tier = settings.omnidapter_free_tier_calls
    billable_calls = max(0, total_calls - free_tier)

    # Simple pricing: $0.005 per billable call
    estimated_cost_cents = billable_calls * 0  # Price TBD

    response = UsageResponse(
        period_start=period_start,
        period_end=period_end,
        total_calls=total_calls,
        free_tier_calls=min(total_calls, free_tier),
        billable_calls=billable_calls,
        estimated_cost_cents=int(estimated_cost_cents),
        by_provider=breakdown["by_provider"],
        by_endpoint=breakdown["by_endpoint"],
    )

    return {
        "data": response,
        "meta": {"request_id": request_id},
    }
