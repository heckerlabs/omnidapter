"""
Typed credential payload models.

These are the auth-kind-specific payloads stored inside a ``StoredCredential``.
Every concrete credential type must inherit from :class:`BaseCredentials` so that
calling code can use ``isinstance(creds, BaseCredentials)`` to distinguish a
credential envelope's payload from arbitrary dicts.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, Field


class BaseCredentials(BaseModel):
    """Base class for all credential payload types.

    ``OAuth2Credentials``, ``ApiKeyCredentials``, and ``BasicCredentials`` all
    inherit from this class.  It is the common base for ``isinstance`` checks
    and an extension point for shared behaviour in future auth kinds.

    Consuming apps that implement custom credential types for non-standard
    auth schemes should also inherit from ``BaseCredentials`` so that
    ``StoredCredential.credentials`` remains uniformly typed.
    """


class OAuth2Credentials(BaseCredentials):
    """OAuth2 token payload."""

    access_token: str
    refresh_token: str | None = None
    token_type: str = "Bearer"
    expires_at: datetime | None = None  # UTC
    id_token: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    def is_expired(self, buffer_seconds: float = 60.0) -> bool:
        """Return True if the access token is expired (or within *buffer_seconds* of expiry)."""
        if self.expires_at is None:
            return False
        return datetime.now(tz=timezone.utc) >= self.expires_at - timedelta(
            seconds=buffer_seconds
        )

    def is_refreshable(self) -> bool:
        """Return True if a refresh_token is available."""
        return self.refresh_token is not None


class ApiKeyCredentials(BaseCredentials):
    """API key auth payload."""

    api_key: str
    header_name: str = "X-API-Key"


class BasicCredentials(BaseCredentials):
    """HTTP Basic auth payload."""

    username: str
    password: str
