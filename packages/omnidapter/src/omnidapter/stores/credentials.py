"""
CredentialStore interface and StoredCredential model.

The consuming app implements CredentialStore. Omnidapter defines the interface.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from omnidapter.auth.models import ApiKeyCredentials, BasicCredentials, OAuth2Credentials
from omnidapter.core.metadata import AuthKind


class StoredCredential(BaseModel):
    """The credential envelope stored by the consuming app."""
    provider_key: str
    auth_kind: AuthKind
    credentials: OAuth2Credentials | ApiKeyCredentials | BasicCredentials
    granted_scopes: list[str] | None = None
    provider_account_id: str | None = None
    provider_config: dict[str, Any] | None = None

    model_config = {"arbitrary_types_allowed": True}


class CredentialStore(ABC):
    """Abstract interface for credential persistence.

    The consuming app implements this. Omnidapter calls it during:
    - Connection resolution
    - Service requests
    - Token refresh
    - OAuth completion
    """

    @abstractmethod
    async def get_credentials(self, connection_id: str) -> StoredCredential | None:
        """Retrieve stored credentials for a connection.

        Returns None if no credentials exist for the given connection_id.
        """
        ...

    @abstractmethod
    async def save_credentials(self, connection_id: str, credentials: StoredCredential) -> None:
        """Persist credentials for a connection."""
        ...

    @abstractmethod
    async def delete_credentials(self, connection_id: str) -> None:
        """Delete credentials for a connection."""
        ...
