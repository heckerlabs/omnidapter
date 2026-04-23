"""Link token response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class LinkTokenData(BaseModel):
    token: str
    expires_at: datetime
    connect_url: str
