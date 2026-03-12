"""
Base provider interface that all providers must implement.

connection_id
─────────────
A ``connection_id`` is an **opaque, caller-managed string** passed into every
provider method that needs to identify which connected account to act on.
Omnidapter never generates or validates ``connection_id`` values; it passes
them through unchanged.

See :mod:`omnidapter.stores.credentials` for a full explanation.
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
        scope_separator: str = " ",
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.authorization_endpoint = authorization_endpoint
        self.token_endpoint = token_endpoint
        self.default_scopes = default_scopes or []
        self.supports_pkce = supports_pkce
        self.extra_auth_params = extra_auth_params or {}
        self.scope_separator = scope_separator


class BaseProvider(ABC):
    """Abstract base class for all provider implementations.

    Every provider must define:
    - ``metadata``: :class:`~omnidapter.core.metadata.ProviderMetadata`
    - ``get_oauth_config()``: :class:`OAuthConfig` or ``None``
    - ``exchange_code_for_tokens()``: returns :class:`~omnidapter.stores.credentials.StoredCredential`
    - ``refresh_token()``: returns :class:`~omnidapter.stores.credentials.StoredCredential`
    - ``get_calendar_service()``: returns a CalendarService
    """

    @property
    @abstractmethod
    def metadata(self) -> ProviderMetadata:
        """Provider metadata for introspection."""
        ...

    def get_oauth_config(self) -> OAuthConfig | None:
        """Return OAuth2 configuration, or ``None`` if OAuth is not supported."""
        return None

    async def exchange_code_for_tokens(
        self,
        connection_id: str,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> StoredCredential:
        """Exchange an OAuth2 authorization code for tokens.

        Returns a :class:`~omnidapter.stores.credentials.StoredCredential`
        envelope that the consuming app should persist under *connection_id*.

        Args:
            connection_id: Caller-managed opaque key.  Omnidapter does not
                interpret or store this value itself — the consuming app owns
                it and passes it in.
            code: The authorization code received from the provider.
            redirect_uri: Must match the URI used to start the flow.
            code_verifier: PKCE verifier, required when
                ``OAuthConfig.supports_pkce`` is ``True``.

        Raises:
            NotImplementedError: if the provider does not support OAuth.
        """
        raise NotImplementedError(
            f"Provider {self.metadata.provider_key!r} does not support OAuth code exchange"
        )

    async def refresh_token(self, stored: StoredCredential) -> StoredCredential:
        """Refresh the access token using the stored refresh token.

        Returns an updated :class:`~omnidapter.stores.credentials.StoredCredential`
        that the consuming app should persist under the same ``connection_id``.

        Raises:
            NotImplementedError: if the provider does not support token refresh.
        """
        raise NotImplementedError(
            f"Provider {self.metadata.provider_key!r} does not support token refresh"
        )

    @abstractmethod
    def get_calendar_service(
        self,
        connection_id: str,
        stored_credential: StoredCredential,
        retry_policy: Any = None,
        hooks: Any = None,
    ) -> Any:
        """Instantiate and return a CalendarService for this provider.

        Args:
            connection_id: Caller-managed opaque key identifying the connected
                account.  Passed through to the service for use in error
                context and correlation.
            stored_credential: The live credential envelope for this connection.
            retry_policy: Optional retry policy.
            hooks: Optional transport hooks.
        """
        ...
