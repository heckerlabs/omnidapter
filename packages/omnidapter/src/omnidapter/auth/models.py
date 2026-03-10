"""
Typed credential payload models.

These are the auth-kind-specific payloads stored inside StoredCredential.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class OAuth2Credentials(BaseModel):
    """OAuth2 token payload."""
    access_token: str
    refresh_token: str | None = None
    token_type: str = "Bearer"
    expires_at: datetime | None = None  # UTC
    id_token: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    def is_expired(self, buffer_seconds: float = 60.0) -> bool:
        """Return True if the access token is expired (or within buffer_seconds of expiry)."""
        if self.expires_at is None:
            return False
        now = datetime.now(tz=timezone.utc)
        from datetime import timedelta
        return now >= self.expires_at - timedelta(seconds=buffer_seconds)

    def is_refreshable(self) -> bool:
        """Return True if a refresh_token is available."""
        return self.refresh_token is not None


class ApiKeyCredentials(BaseModel):
    """API key auth payload."""
    api_key: str
    header_name: str = "X-API-Key"


class BasicCredentials(BaseModel):
    """HTTP Basic auth payload."""
    username: str
    password: str
