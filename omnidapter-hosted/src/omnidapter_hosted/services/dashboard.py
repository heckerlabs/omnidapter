"""Dashboard service — profile, tenant, member, and provider config operations."""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_hosted.models.membership import HostedMembership, MemberRole
from omnidapter_hosted.models.tenant import Tenant
from omnidapter_hosted.models.user import HostedUser


def _require_admin(role: str) -> None:
    if role not in (MemberRole.OWNER, MemberRole.ADMIN):
        raise HTTPException(
            status_code=403,
            detail={"code": "forbidden", "message": "Owner or admin role required"},
        )


async def update_user_name(
    user: HostedUser,
    name: str,
    session: AsyncSession,
) -> HostedUser:
    user.name = name
    await session.commit()
    await session.refresh(user)
    return user


async def update_tenant_name(
    tenant: Tenant,
    name: str,
    role: str,
    session: AsyncSession,
) -> Tenant:
    _require_admin(role)
    tenant.name = name
    await session.commit()
    await session.refresh(tenant)
    return tenant


async def list_members(
    tenant_id: uuid.UUID,
    session: AsyncSession,
) -> list[tuple[HostedMembership, HostedUser]]:
    result = await session.execute(
        select(HostedMembership, HostedUser)
        .join(HostedUser, HostedUser.id == HostedMembership.user_id)
        .where(HostedMembership.tenant_id == tenant_id)
    )
    return list(result.all())


async def remove_member(
    tenant_id: uuid.UUID,
    target_user_id: uuid.UUID,
    requesting_role: str,
    requesting_user_id: uuid.UUID,
    session: AsyncSession,
) -> None:
    _require_admin(requesting_role)

    result = await session.execute(
        select(HostedMembership)
        .where(HostedMembership.tenant_id == tenant_id)
        .where(HostedMembership.user_id == target_user_id)
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Member not found"})

    if membership.role == MemberRole.OWNER:
        raise HTTPException(
            status_code=400,
            detail={"code": "cannot_remove_owner", "message": "Cannot remove the tenant owner"},
        )

    if target_user_id == requesting_user_id:
        raise HTTPException(
            status_code=400,
            detail={"code": "cannot_remove_self", "message": "Cannot remove yourself"},
        )

    await session.delete(membership)
    await session.commit()
