"""Membership management endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from omnidapter_server.database import get_session
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_hosted.dependencies import (
    HostedAuthContext,
    get_hosted_auth_context,
    get_request_id,
)
from omnidapter_hosted.models.membership import HostedMembership, MemberRole

router = APIRouter(prefix="/memberships", tags=["memberships"])


class MembershipResponse(BaseModel):
    id: str
    tenant_id: str
    user_id: str
    role: str
    created_at: str

    @classmethod
    def from_model(cls, m: HostedMembership) -> MembershipResponse:
        return cls(
            id=str(m.id),
            tenant_id=str(m.tenant_id),
            user_id=str(m.user_id),
            role=m.role,
            created_at=m.created_at.isoformat(),
        )


class CreateMembershipRequest(BaseModel):
    user_id: str
    role: str = MemberRole.MEMBER


@router.get("")
async def list_memberships(
    auth: Annotated[HostedAuthContext, Depends(get_hosted_auth_context)],
    session: AsyncSession = Depends(get_session),
    request_id: str = Depends(get_request_id),
):
    result = await session.execute(
        select(HostedMembership).where(HostedMembership.tenant_id == auth.tenant_id)
    )
    memberships = result.scalars().all()
    return {
        "data": [MembershipResponse.from_model(m) for m in memberships],
        "meta": {"request_id": request_id},
    }


@router.post("", status_code=201)
async def create_membership(
    body: CreateMembershipRequest,
    auth: Annotated[HostedAuthContext, Depends(get_hosted_auth_context)],
    session: AsyncSession = Depends(get_session),
    request_id: str = Depends(get_request_id),
):
    try:
        user_uuid = uuid.UUID(body.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid user_id") from exc

    # Check duplicate
    result = await session.execute(
        select(HostedMembership).where(
            HostedMembership.tenant_id == auth.tenant_id,
            HostedMembership.user_id == user_uuid,
        )
    )
    if result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="User is already a member")

    membership = HostedMembership(
        id=uuid.uuid4(),
        tenant_id=auth.tenant_id,
        user_id=user_uuid,
        role=body.role,
    )
    session.add(membership)
    await session.commit()
    await session.refresh(membership)
    return {
        "data": MembershipResponse.from_model(membership),
        "meta": {"request_id": request_id},
    }


@router.delete("/{membership_id}", status_code=204)
async def delete_membership(
    membership_id: str,
    auth: Annotated[HostedAuthContext, Depends(get_hosted_auth_context)],
    session: AsyncSession = Depends(get_session),
):
    try:
        m_uuid = uuid.UUID(membership_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Membership not found") from exc

    result = await session.execute(
        select(HostedMembership).where(
            HostedMembership.id == m_uuid,
            HostedMembership.tenant_id == auth.tenant_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Membership not found")

    await session.execute(delete(HostedMembership).where(HostedMembership.id == m_uuid))
    await session.commit()
