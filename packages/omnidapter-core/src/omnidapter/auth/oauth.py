"""
OAuth 2.0 flow helpers — begin and complete flows.
"""

from __future__ import annotations

import hashlib
import secrets
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from omnidapter.core.logging import auth_logger

if TYPE_CHECKING:
    import httpx

    from omnidapter.core.registry import ProviderRegistry
    from omnidapter.stores.credentials import CredentialStore
    from omnidapter.stores.oauth_state import OAuthStateStore
    from omnidapter.transport.hooks import TransportHooks
    from omnidapter.transport.retry import RetryPolicy


class OAuthBeginResult(BaseModel):
    """Result of beginning an OAuth flow."""

    authorization_url: str
    state: str
    connection_id: str
    provider: str


class OAuthPendingState(BaseModel):
    """Payload stored in the OAuthStateStore during a pending OAuth flow."""

    connection_id: str
    provider: str
    redirect_uri: str
    code_verifier: str | None = None
    expires_at: datetime  # UTC


def _generate_pkce_pair() -> tuple[str, str]:
    """Generate a PKCE code_verifier and code_challenge pair (S256 method)."""
    import base64

    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    return verifier, challenge


class OAuthHelper:
    """Manages OAuth begin/complete flows with automatic credential persistence."""

    def __init__(
        self,
        registry: ProviderRegistry,
        credential_store: CredentialStore,
        oauth_state_store: OAuthStateStore,
        retry_policy: RetryPolicy | None = None,
        hooks: TransportHooks | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._registry = registry
        self._credential_store = credential_store
        self._oauth_state_store = oauth_state_store
        self._retry_policy = retry_policy
        self._hooks = hooks
        self._http_client = http_client

    def _configure_provider_transport(self, provider_impl: Any) -> None:
        configure = getattr(provider_impl, "configure_oauth_transport", None)
        if callable(configure):
            configure(
                retry_policy=self._retry_policy,
                hooks=self._hooks,
                http_client=self._http_client,
            )

    async def begin(
        self,
        provider: str,
        connection_id: str,
        redirect_uri: str,
        scopes: list[str] | None = None,
        extra_params: dict[str, str] | None = None,
    ) -> OAuthBeginResult:
        """Begin an OAuth flow.

        Generates authorization URL, persists temporary state, returns the redirect URL.
        """
        provider_impl = self._registry.get(provider)
        oauth_config = provider_impl.get_oauth_config()
        if oauth_config is None:
            raise ValueError(f"Provider {provider!r} does not support OAuth2")

        state_id = secrets.token_urlsafe(32)
        code_verifier: str | None = None

        params: dict[str, str] = {
            "response_type": "code",
            "client_id": oauth_config.client_id,
            "redirect_uri": redirect_uri,
            "state": state_id,
        }

        # Scopes
        effective_scopes = scopes or oauth_config.default_scopes
        if effective_scopes:
            params["scope"] = oauth_config.scope_separator.join(effective_scopes)

        # Provider-defined extra params (e.g. access_type=offline for Google)
        if oauth_config.extra_auth_params:
            params.update(oauth_config.extra_auth_params)

        # PKCE
        if oauth_config.supports_pkce:
            code_verifier, code_challenge = _generate_pkce_pair()
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"

        # Caller overrides last so they can always override provider defaults
        if extra_params:
            params.update(extra_params)

        authorization_url = (
            oauth_config.authorization_endpoint + "?" + urllib.parse.urlencode(params)
        )

        pending = OAuthPendingState(
            connection_id=connection_id,
            provider=provider,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
            expires_at=datetime.now(tz=timezone.utc) + timedelta(minutes=15),
        )

        await self._oauth_state_store.save_state(
            state_id=state_id,
            payload=pending.model_dump(mode="json"),
            expires_at=pending.expires_at,
        )

        auth_logger.info(
            "OAuth begin: provider=%r connection_id=%r state=%r",
            provider,
            connection_id,
            state_id,
        )

        return OAuthBeginResult(
            authorization_url=authorization_url,
            state=state_id,
            connection_id=connection_id,
            provider=provider,
        )

    async def complete(
        self,
        provider: str,
        connection_id: str,
        code: str,
        state: str,
        redirect_uri: str,
    ) -> Any:
        """Complete an OAuth flow.

        Validates state, exchanges code for tokens, persists credentials.

        Returns:
            The StoredCredential (for inspection only — already persisted).
        """
        from omnidapter.core.errors import OAuthStateError

        # Load and validate state
        state_payload = await self._oauth_state_store.load_state(state)
        if state_payload is None:
            raise OAuthStateError("OAuth state not found or expired")

        pending = OAuthPendingState.model_validate(state_payload)

        if pending.connection_id != connection_id:
            raise OAuthStateError("OAuth state connection_id mismatch")
        if pending.provider != provider:
            raise OAuthStateError("OAuth state provider mismatch")
        if pending.redirect_uri != redirect_uri:
            raise OAuthStateError("OAuth state redirect_uri mismatch")

        # Exchange code for tokens
        provider_impl = self._registry.get(provider)
        self._configure_provider_transport(provider_impl)
        stored_credential = await provider_impl.exchange_code_for_tokens(
            connection_id=connection_id,
            code=code,
            redirect_uri=redirect_uri,
            code_verifier=pending.code_verifier,
        )

        # Persist credentials
        await self._credential_store.save_credentials(connection_id, stored_credential)

        # Clean up state
        await self._oauth_state_store.delete_state(state)

        auth_logger.info(
            "OAuth complete: provider=%r connection_id=%r",
            provider,
            connection_id,
        )

        return stored_credential
