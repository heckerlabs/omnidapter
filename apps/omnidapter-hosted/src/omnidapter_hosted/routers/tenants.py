"""Tenant management endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from omnidapter_server.database import get_session
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_hosted.dependencies import (
    HostedAuthContext,
    get_hosted_auth_context,
    get_request_id,
)
from omnidapter_hosted.models.tenant import Tenant, TenantPlan

router = APIRouter(prefix="/tenants", tags=["tenants"])


class TenantResponse(BaseModel):
    id: str
    name: str
    plan: str
    is_active: bool
    stripe_customer_id: str | None
    created_at: str

    @classmethod
    def from_model(cls, t: Tenant) -> TenantResponse:
        return cls(
            id=str(t.id),
            name=t.name,
            plan=t.plan,
            is_active=t.is_active,
            stripe_customer_id=t.stripe_customer_id,
            created_at=t.created_at.isoformat(),
        )


class CreateTenantRequest(BaseModel):
    name: str
    plan: str = TenantPlan.FREE


@router.get("/me")
async def get_current_tenant(
    auth: Annotated[HostedAuthContext, Depends(get_hosted_auth_context)],
    session: AsyncSession = Depends(get_session),
    request_id: str = Depends(get_request_id),
):
    result = await session.execute(select(Tenant).where(Tenant.id == auth.tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {"data": TenantResponse.from_model(tenant), "meta": {"request_id": request_id}}


@router.post("", status_code=201)
async def create_tenant(
    body: CreateTenantRequest,
    session: AsyncSession = Depends(get_session),
    request_id: str = Depends(get_request_id),
):
    tenant = Tenant(
        id=uuid.uuid4(),
        name=body.name,
        plan=body.plan,
        is_active=True,
    )
    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)
    return {"data": TenantResponse.from_model(tenant), "meta": {"request_id": request_id}}
