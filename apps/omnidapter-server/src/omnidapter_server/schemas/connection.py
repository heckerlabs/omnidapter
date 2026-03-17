"""Connection schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class CreateConnectionRequest(BaseModel):
    provider: str
    external_id: str | None = None
    redirect_url: str
    metadata: dict[str, Any] | None = None


class ReauthorizeConnectionRequest(BaseModel):
    redirect_url: str


class ConnectionResponse(BaseModel):
    id: str
    provider: str
    external_id: str | None
    status: str
    status_reason: str | None
    granted_scopes: list[str] | None
    provider_account_id: str | None
    created_at: datetime
    last_used_at: datetime | None

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, conn: Any) -> ConnectionResponse:
        return cls(
            id=str(conn.id),
            provider=conn.provider_key,
            external_id=conn.external_id,
            status=conn.status,
            status_reason=conn.status_reason,
            granted_scopes=conn.granted_scopes,
            provider_account_id=conn.provider_account_id,
            created_at=conn.created_at,
            last_used_at=conn.last_used_at,
        )


class CreateConnectionResponse(BaseModel):
    connection_id: str
    status: str
    authorization_url: str
