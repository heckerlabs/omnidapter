from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OAuth2Credentials(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "Bearer"
    expires_at: datetime | None = None
    scope: list[str] = Field(default_factory=list)

    def is_expired(self, skew_seconds: int = 30) -> bool:
        if self.expires_at is None:
            return False
        now = datetime.now(timezone.utc)
        expires = self.expires_at.astimezone(timezone.utc)
        return now.timestamp() + skew_seconds >= expires.timestamp()


class ApiKeyCredentials(BaseModel):
    api_key: str
    header_name: str = "Authorization"
    prefix: str | None = None


class BasicCredentials(BaseModel):
    username: str
    password: str


class OAuthBeginResult(BaseModel):
    authorization_url: str
    state: str
    expires_at: datetime


class OAuthStatePayload(BaseModel):
    provider: str
    connection_id: str
    code_verifier: str
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class OAuthTokenResult(BaseModel):
    credentials: OAuth2Credentials
    granted_scopes: list[str] = Field(default_factory=list)
    provider_account_id: str | None = None


CredentialPayload = OAuth2Credentials | ApiKeyCredentials | BasicCredentials


class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
