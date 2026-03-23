"""Provider config schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class UpsertProviderConfigRequest(BaseModel):
    client_id: str
    client_secret: str
    scopes: list[str] | None = None


class ProviderConfigResponse(BaseModel):
    id: str
    provider_key: str
    auth_kind: str
    scopes: list[str] | None
    is_fallback: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, cfg: Any) -> ProviderConfigResponse:
        return cls(
            id=str(cfg.id),
            provider_key=cfg.provider_key,
            auth_kind=cfg.auth_kind,
            scopes=cfg.scopes,
            is_fallback=cfg.is_fallback,
            created_at=cfg.created_at,
            updated_at=cfg.updated_at,
        )
