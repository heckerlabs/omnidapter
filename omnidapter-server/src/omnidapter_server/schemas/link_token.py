"""Link token response schemas."""

from __future__ import annotations

from pydantic import BaseModel


class LinkTokenData(BaseModel):
    token: str
    expires_at: str
    connect_url: str
