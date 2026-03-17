"""Hosted API key management endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from omnidapter_server.database import get_session
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_hosted.dependencies import (
    HostedAuthContext,
    get_hosted_auth_context,
    get_request_id,
)
from omnidapter_hosted.models.api_key import HostedAPIKey
from omnidapter_hosted.services.auth import generate_hosted_api_key

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


class APIKeyResponse(BaseModel):
    id: str
    name: str
    key_prefix: str
    is_active: bool
    is_test: bool
    last_used_at: str | None
    created_at: str

    @classmethod
    def from_model(cls, k: HostedAPIKey) -> APIKeyResponse:
        return cls(
            id=str(k.id),
            name=k.name,
            key_prefix=k.key_prefix,
            is_active=k.is_active,
            is_test=k.is_test,
            last_used_at=k.last_used_at.isoformat() if k.last_used_at else None,
            created_at=k.created_at.isoformat(),
        )


class CreateAPIKeyResponse(APIKeyResponse):
    raw_key: str  # Only returned on creation


class CreateAPIKeyRequest(BaseModel):
    name: str
    is_test: bool = False


@router.get("")
async def list_api_keys(
    auth: Annotated[HostedAuthContext, Depends(get_hosted_auth_context)],
    session: AsyncSession = Depends(get_session),
    request_id: str = Depends(get_request_id),
):
    result = await session.execute(
        select(HostedAPIKey).where(HostedAPIKey.tenant_id == auth.tenant_id)
    )
    keys = result.scalars().all()
    return {
        "data": [APIKeyResponse.from_model(k) for k in keys],
        "meta": {"request_id": request_id},
    }


@router.post("", status_code=201)
async def create_api_key(
    body: CreateAPIKeyRequest,
    auth: Annotated[HostedAuthContext, Depends(get_hosted_auth_context)],
    session: AsyncSession = Depends(get_session),
    request_id: str = Depends(get_request_id),
):
    raw_key, key_hash, key_prefix = generate_hosted_api_key(is_test=body.is_test)
    api_key = HostedAPIKey(
        id=uuid.uuid4(),
        tenant_id=auth.tenant_id,
        name=body.name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        is_active=True,
        is_test=body.is_test,
    )
    session.add(api_key)
    await session.commit()
    await session.refresh(api_key)

    response_data = APIKeyResponse.from_model(api_key).model_dump()
    response_data["raw_key"] = raw_key

    return {"data": response_data, "meta": {"request_id": request_id}}


@router.delete("/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: str,
    auth: Annotated[HostedAuthContext, Depends(get_hosted_auth_context)],
    session: AsyncSession = Depends(get_session),
):
    try:
        key_uuid = uuid.UUID(key_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="API key not found") from exc

    result = await session.execute(
        select(HostedAPIKey).where(
            HostedAPIKey.id == key_uuid, HostedAPIKey.tenant_id == auth.tenant_id
        )
    )
    key = result.scalar_one_or_none()
    if key is None:
        raise HTTPException(status_code=404, detail="API key not found")

    await session.execute(
        update(HostedAPIKey).where(HostedAPIKey.id == key_uuid).values(is_active=False)
    )
    await session.commit()
