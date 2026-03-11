"""
CredentialStore interface and StoredCredential model.

connection_id
─────────────
A ``connection_id`` is an **opaque, caller-managed string** that Omnidapter
uses as the key into a ``CredentialStore``.  Omnidapter never generates,
validates, or transforms ``connection_id`` values — the consuming application
is fully responsible for them.

Typical choices are a UUID generated at OAuth completion time, or a composite
key such as ``"{user_id}:{provider}"``.  Whatever scheme the app uses,
Omnidapter passes the same string back verbatim when resolving credentials for
a service call, persisting refreshed tokens, or looking up OAuth state.

The consuming app is responsible for:
  * Creating a ``connection_id`` when a user first connects a provider.
  * Storing the mapping of ``connection_id`` → user / account in its own DB.
  * Supplying the ``connection_id`` to ``Omnidapter.connection()``,
    ``provider.get_calendar_service()``, and
    ``provider.exchange_code_for_tokens()``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from omnidapter.auth.models import ApiKeyCredentials, BasicCredentials, OAuth2Credentials
from omnidapter.core.metadata import AuthKind


class StoredCredential(BaseModel):
    """Credential envelope persisted by the consuming app.

    ``credentials`` holds the auth-kind-specific payload.  All payload types
    inherit from :class:`~omnidapter.auth.models.BaseCredentials`, so
    ``isinstance(stored.credentials, BaseCredentials)`` is always ``True``.
    """

    provider_key: str
    auth_kind: AuthKind
    credentials: OAuth2Credentials | ApiKeyCredentials | BasicCredentials
    granted_scopes: list[str] | None = None
    provider_account_id: str | None = None
    provider_config: dict[str, Any] | None = None


class CredentialStore(ABC):
    """Abstract interface for credential persistence.

    The consuming app implements this interface; Omnidapter calls it when
    resolving a ``connection_id`` to live credentials, persisting refreshed
    tokens, and completing the OAuth flow.

    All methods receive a ``connection_id`` — see the module docstring for a
    full explanation of what ``connection_id`` is and who owns it.
    """

    @abstractmethod
    async def get_credentials(self, connection_id: str) -> StoredCredential | None:
        """Return the stored credential for *connection_id*, or ``None``.

        Args:
            connection_id: Caller-managed opaque key identifying a connected
                account.  Omnidapter passes this through unchanged.
        """
        ...

    @abstractmethod
    async def save_credentials(self, connection_id: str, credentials: StoredCredential) -> None:
        """Persist *credentials* under *connection_id*.

        Called after OAuth completion and after every successful token refresh.

        Args:
            connection_id: Caller-managed opaque key.
            credentials: Full credential envelope to persist.
        """
        ...

    @abstractmethod
    async def delete_credentials(self, connection_id: str) -> None:
        """Delete the credential stored under *connection_id*.

        Args:
            connection_id: Caller-managed opaque key.
        """
        ...
