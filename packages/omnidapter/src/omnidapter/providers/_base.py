"""
Base provider interface that all providers must implement.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from omnidapter.core.metadata import ProviderMetadata
    from omnidapter.stores.credentials import StoredCredential


class OAuthConfig:
    """OAuth2 configuration for a provider."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        authorization_endpoint: str,
        token_endpoint: str,
        default_scopes: list[str] | None = None,
        supports_pkce: bool = False,
        extra_auth_params: dict[str, str] | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.authorization_endpoint = authorization_endpoint
        self.token_endpoint = token_endpoint
        self.default_scopes = default_scopes or []
        self.supports_pkce = supports_pkce
        self.extra_auth_params = extra_auth_params or {}


class BaseProvider(ABC):
    """Abstract base class for all provider implementations.

    Every provider must define:
    - metadata: ProviderMetadata
    - get_oauth_config(): OAuthConfig | None
    - exchange_code_for_tokens(): StoredCredential
    - refresh_token(): StoredCredential
    - get_calendar_service(): CalendarService
    """

    @property
    @abstractmethod
    def metadata(self) -> "ProviderMetadata":
        """Provider metadata for introspection."""
        ...

    def get_oauth_config(self) -> OAuthConfig | None:
        """Return OAuth2 configuration or None if OAuth is not supported."""
        return None

    async def exchange_code_for_tokens(
        self,
        connection_id: str,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> "StoredCredential":
        """Exchange an authorization code for tokens.

        Returns a StoredCredential envelope.
        Raises: NotImplementedError if the provider does not support OAuth.
        """
        raise NotImplementedError(
            f"Provider {self.metadata.provider_key!r} does not support OAuth code exchange"
        )

    async def refresh_token(self, stored: "StoredCredential") -> "StoredCredential":
        """Refresh the access token.

        Returns an updated StoredCredential.
        Raises: NotImplementedError if the provider does not support token refresh.
        """
        raise NotImplementedError(
            f"Provider {self.metadata.provider_key!r} does not support token refresh"
        )

    @abstractmethod
    def get_calendar_service(
        self,
        connection_id: str,
        stored_credential: "StoredCredential",
        retry_policy: Any = None,
        hooks: Any = None,
    ) -> Any:
        """Instantiate and return a CalendarService for this provider."""
        ...
