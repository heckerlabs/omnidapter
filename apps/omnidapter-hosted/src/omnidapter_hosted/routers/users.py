"""User management endpoints."""

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
from omnidapter_hosted.models.user import HostedUser

router = APIRouter(prefix="/users", tags=["users"])


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    created_at: str

    @classmethod
    def from_model(cls, u: HostedUser) -> UserResponse:
        return cls(
            id=str(u.id),
            email=u.email,
            name=u.name,
            created_at=u.created_at.isoformat(),
        )


class CreateUserRequest(BaseModel):
    email: str
    name: str
    workos_user_id: str | None = None


@router.post("", status_code=201)
async def create_user(
    body: CreateUserRequest,
    session: AsyncSession = Depends(get_session),
    request_id: str = Depends(get_request_id),
):
    # Check for existing email
    result = await session.execute(select(HostedUser).where(HostedUser.email == body.email))
    existing = result.scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409, detail={"code": "email_taken", "message": "Email already in use"}
        )

    user = HostedUser(
        id=uuid.uuid4(),
        email=body.email,
        name=body.name,
        workos_user_id=body.workos_user_id,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return {"data": UserResponse.from_model(user), "meta": {"request_id": request_id}}


@router.get("/{user_id}")
async def get_user(
    user_id: str,
    auth: Annotated[HostedAuthContext, Depends(get_hosted_auth_context)],
    session: AsyncSession = Depends(get_session),
    request_id: str = Depends(get_request_id),
):
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="User not found") from exc

    result = await session.execute(select(HostedUser).where(HostedUser.id == user_uuid))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return {"data": UserResponse.from_model(user), "meta": {"request_id": request_id}}
