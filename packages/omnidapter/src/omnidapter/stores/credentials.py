from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field

from omnidapter.auth.kinds import AuthKind
from omnidapter.auth.models import CredentialPayload


class StoredCredential(BaseModel):
    provider_key: str
    auth_kind: AuthKind
    credentials: CredentialPayload
    granted_scopes: list[str] | None = None
    provider_account_id: str | None = None
    provider_config: dict[str, Any] | None = Field(default=None)


class CredentialStore(Protocol):
    async def get_credentials(self, connection_id: str) -> StoredCredential | None: ...

    async def save_credentials(self, connection_id: str, credentials: StoredCredential) -> None: ...

    async def delete_credentials(self, connection_id: str) -> None: ...
