"""
Unit tests for omnidapter.auth.oauth.OAuthHelper and helpers.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from omnidapter.auth.oauth import (
    OAuthBeginResult,
    OAuthHelper,
    OAuthPendingState,
    _generate_pkce_pair,
)
from omnidapter.core.errors import OAuthStateError
from omnidapter.stores.credentials import StoredCredential
from omnidapter.testing.fakes.stores import InMemoryCredentialStore, InMemoryOAuthStateStore

# --------------------------------------------------------------------------- #
# _generate_pkce_pair                                                          #
# --------------------------------------------------------------------------- #


class TestGeneratePkcePair:
    def test_returns_two_strings(self):
        verifier, challenge = _generate_pkce_pair()
        assert isinstance(verifier, str)
        assert isinstance(challenge, str)

    def test_verifier_and_challenge_differ(self):
        verifier, challenge = _generate_pkce_pair()
        assert verifier != challenge

    def test_unique_on_each_call(self):
        v1, _ = _generate_pkce_pair()
        v2, _ = _generate_pkce_pair()
        assert v1 != v2

    def test_challenge_is_base64url(self):
        _, challenge = _generate_pkce_pair()
        # base64url chars only (no +, /, =)
        assert "+" not in challenge
        assert "/" not in challenge
        assert "=" not in challenge


# --------------------------------------------------------------------------- #
# OAuthHelper.begin                                                            #
# --------------------------------------------------------------------------- #


def _make_helper(supports_pkce: bool = False):
    from omnidapter.providers._base import OAuthConfig

    oauth_config = OAuthConfig(
        client_id="client-id",
        client_secret="client-secret",
        authorization_endpoint="https://provider.example/auth",
        token_endpoint="https://provider.example/token",
        default_scopes=["calendar.read"],
        supports_pkce=supports_pkce,
    )
    mock_provider = MagicMock()
    mock_provider.get_oauth_config.return_value = oauth_config

    registry = MagicMock()
    registry.get.return_value = mock_provider

    state_store = InMemoryOAuthStateStore()
    cred_store = InMemoryCredentialStore()

    helper = OAuthHelper(
        registry=registry,
        credential_store=cred_store,
        oauth_state_store=state_store,
    )
    return helper, state_store, cred_store, registry


class TestOAuthHelperBegin:
    async def test_returns_begin_result(self):
        helper, _, _, _ = _make_helper()
        result = await helper.begin(
            provider="test_provider",
            connection_id="conn-1",
            redirect_uri="https://app.example/callback",
        )
        assert isinstance(result, OAuthBeginResult)
        assert result.connection_id == "conn-1"
        assert result.provider == "test_provider"
        assert result.state
        assert "https://provider.example/auth" in result.authorization_url

    async def test_authorization_url_contains_client_id(self):
        helper, _, _, _ = _make_helper()
        result = await helper.begin("p", "conn-1", "https://app.example/cb")
        assert "client_id=client-id" in result.authorization_url

    async def test_authorization_url_contains_redirect_uri(self):
        helper, _, _, _ = _make_helper()
        result = await helper.begin("p", "conn-1", "https://app.example/cb")
        assert "redirect_uri=" in result.authorization_url

    async def test_default_scopes_in_url(self):
        helper, _, _, _ = _make_helper()
        result = await helper.begin("p", "conn-1", "https://app.example/cb")
        assert "scope=" in result.authorization_url
        assert "calendar.read" in result.authorization_url

    async def test_custom_scopes_override_defaults(self):
        helper, _, _, _ = _make_helper()
        result = await helper.begin(
            "p", "conn-1", "https://app.example/cb", scopes=["custom.scope"]
        )
        assert "custom.scope" in result.authorization_url
        assert "calendar.read" not in result.authorization_url

    async def test_state_saved_in_store(self):
        helper, state_store, _, _ = _make_helper()
        result = await helper.begin("p", "conn-1", "https://app.example/cb")
        payload = await state_store.load_state(result.state)
        assert payload is not None
        assert payload["connection_id"] == "conn-1"

    async def test_pkce_params_in_url_when_supported(self):
        helper, _, _, _ = _make_helper(supports_pkce=True)
        result = await helper.begin("p", "conn-1", "https://app.example/cb")
        assert "code_challenge=" in result.authorization_url
        assert "code_challenge_method=S256" in result.authorization_url

    async def test_no_pkce_when_not_supported(self):
        helper, _, _, _ = _make_helper(supports_pkce=False)
        result = await helper.begin("p", "conn-1", "https://app.example/cb")
        assert "code_challenge" not in result.authorization_url

    async def test_non_oauth_provider_raises(self):
        registry = MagicMock()
        mock_provider = MagicMock()
        mock_provider.get_oauth_config.return_value = None
        registry.get.return_value = mock_provider

        helper = OAuthHelper(
            registry=registry,
            credential_store=InMemoryCredentialStore(),
            oauth_state_store=InMemoryOAuthStateStore(),
        )
        with pytest.raises(ValueError, match="does not support OAuth2"):
            await helper.begin("no_oauth", "conn-1", "https://app.example/cb")

    async def test_extra_params_appended(self):
        helper, _, _, _ = _make_helper()
        result = await helper.begin(
            "p",
            "conn-1",
            "https://app.example/cb",
            extra_params={"prompt": "consent"},
        )
        assert "prompt=consent" in result.authorization_url

    async def test_provider_extra_auth_params_included(self):
        """OAuthConfig.extra_auth_params are baked into the authorization URL."""
        from omnidapter.providers._base import OAuthConfig

        oauth_config = OAuthConfig(
            client_id="cid",
            client_secret="cs",
            authorization_endpoint="https://provider.example/auth",
            token_endpoint="https://provider.example/token",
            extra_auth_params={"access_type": "offline", "prompt": "consent"},
        )
        mock_provider = MagicMock()
        mock_provider.get_oauth_config.return_value = oauth_config
        registry = MagicMock()
        registry.get.return_value = mock_provider

        helper = OAuthHelper(
            registry=registry,
            credential_store=InMemoryCredentialStore(),
            oauth_state_store=InMemoryOAuthStateStore(),
        )
        result = await helper.begin("p", "conn-1", "https://app.example/cb")
        assert "access_type=offline" in result.authorization_url
        assert "prompt=consent" in result.authorization_url

    async def test_caller_extra_params_override_provider_extra_auth_params(self):
        """Caller-supplied extra_params win over provider defaults."""
        from omnidapter.providers._base import OAuthConfig

        oauth_config = OAuthConfig(
            client_id="cid",
            client_secret="cs",
            authorization_endpoint="https://provider.example/auth",
            token_endpoint="https://provider.example/token",
            extra_auth_params={"prompt": "consent"},
        )
        mock_provider = MagicMock()
        mock_provider.get_oauth_config.return_value = oauth_config
        registry = MagicMock()
        registry.get.return_value = mock_provider

        helper = OAuthHelper(
            registry=registry,
            credential_store=InMemoryCredentialStore(),
            oauth_state_store=InMemoryOAuthStateStore(),
        )
        result = await helper.begin(
            "p", "conn-1", "https://app.example/cb", extra_params={"prompt": "select_account"}
        )
        assert "prompt=select_account" in result.authorization_url
        assert "prompt=consent" not in result.authorization_url

    async def test_scope_separator_respected(self):
        """Scopes are joined using OAuthConfig.scope_separator."""
        import urllib.parse

        from omnidapter.providers._base import OAuthConfig

        oauth_config = OAuthConfig(
            client_id="cid",
            client_secret="cs",
            authorization_endpoint="https://provider.example/auth",
            token_endpoint="https://provider.example/token",
            default_scopes=["Calendar.ALL", "Event.ALL"],
            scope_separator=",",
        )
        mock_provider = MagicMock()
        mock_provider.get_oauth_config.return_value = oauth_config
        registry = MagicMock()
        registry.get.return_value = mock_provider

        helper = OAuthHelper(
            registry=registry,
            credential_store=InMemoryCredentialStore(),
            oauth_state_store=InMemoryOAuthStateStore(),
        )
        result = await helper.begin("p", "conn-1", "https://app.example/cb")
        parsed = urllib.parse.parse_qs(urllib.parse.urlsplit(result.authorization_url).query)
        assert parsed["scope"] == ["Calendar.ALL,Event.ALL"]


# --------------------------------------------------------------------------- #
# OAuthHelper.complete                                                         #
# --------------------------------------------------------------------------- #


def _make_stored_credential(provider_key: str = "p") -> StoredCredential:
    from omnidapter.auth.models import OAuth2Credentials
    from omnidapter.core.metadata import AuthKind

    return StoredCredential(
        provider_key=provider_key,
        auth_kind=AuthKind.OAUTH2,
        credentials=OAuth2Credentials(access_token="at", refresh_token="rt"),
    )


class TestOAuthHelperComplete:
    async def _setup_pending_state(self, state_store, connection_id="conn-1", provider="p"):
        pending = OAuthPendingState(
            connection_id=connection_id,
            provider=provider,
            redirect_uri="https://app.example/cb",
            expires_at=datetime.now(tz=timezone.utc) + timedelta(minutes=10),
        )
        state_id = "state-abc"
        await state_store.save_state(state_id, pending.model_dump(mode="json"), pending.expires_at)
        return state_id

    async def test_complete_returns_stored_credential(self):
        helper, state_store, cred_store, registry = _make_helper()
        state_id = await self._setup_pending_state(state_store)

        stored = _make_stored_credential("p")
        mock_provider = MagicMock()
        mock_provider.exchange_code_for_tokens = AsyncMock(return_value=stored)
        registry.get.return_value = mock_provider

        result = await helper.complete(
            "p", "conn-1", "code-xyz", state_id, "https://app.example/cb"
        )
        assert result is stored

    async def test_credentials_persisted_after_complete(self):
        helper, state_store, cred_store, registry = _make_helper()
        state_id = await self._setup_pending_state(state_store)

        stored = _make_stored_credential("p")
        mock_provider = MagicMock()
        mock_provider.exchange_code_for_tokens = AsyncMock(return_value=stored)
        registry.get.return_value = mock_provider

        await helper.complete("p", "conn-1", "code-xyz", state_id, "https://app.example/cb")
        saved = await cred_store.get_credentials("conn-1")
        assert saved is stored

    async def test_state_deleted_after_complete(self):
        helper, state_store, cred_store, registry = _make_helper()
        state_id = await self._setup_pending_state(state_store)

        stored = _make_stored_credential("p")
        mock_provider = MagicMock()
        mock_provider.exchange_code_for_tokens = AsyncMock(return_value=stored)
        registry.get.return_value = mock_provider

        await helper.complete("p", "conn-1", "code-xyz", state_id, "https://app.example/cb")
        assert await state_store.load_state(state_id) is None

    async def test_complete_configures_provider_transport(self):
        from omnidapter.transport.retry import RetryPolicy

        retry_policy = RetryPolicy.no_retry()
        shared_client = MagicMock()
        registry = MagicMock()
        state_store = InMemoryOAuthStateStore()
        cred_store = InMemoryCredentialStore()
        helper = OAuthHelper(
            registry=registry,
            credential_store=cred_store,
            oauth_state_store=state_store,
            retry_policy=retry_policy,
            http_client=shared_client,
        )
        state_id = await self._setup_pending_state(state_store)

        stored = _make_stored_credential("p")
        mock_provider = MagicMock()
        mock_provider.exchange_code_for_tokens = AsyncMock(return_value=stored)
        registry.get.return_value = mock_provider

        await helper.complete("p", "conn-1", "code-xyz", state_id, "https://app.example/cb")

        mock_provider.configure_oauth_transport.assert_called_once_with(
            retry_policy=retry_policy,
            hooks=None,
            http_client=shared_client,
        )

    async def test_missing_state_raises_oauth_state_error(self):
        helper, _, _, _ = _make_helper()
        with pytest.raises(OAuthStateError, match="not found"):
            await helper.complete("p", "conn-1", "code", "nonexistent-state", "https://r")

    async def test_connection_id_mismatch_raises(self):
        helper, state_store, _, _ = _make_helper()
        state_id = await self._setup_pending_state(state_store, connection_id="conn-X")
        with pytest.raises(OAuthStateError, match="connection_id mismatch"):
            await helper.complete("p", "conn-DIFFERENT", "code", state_id, "https://r")

    async def test_provider_mismatch_raises(self):
        helper, state_store, _, _ = _make_helper()
        state_id = await self._setup_pending_state(state_store, provider="provider-A")
        with pytest.raises(OAuthStateError, match="provider mismatch"):
            await helper.complete("provider-B", "conn-1", "code", state_id, "https://r")

    async def test_redirect_uri_mismatch_raises(self):
        helper, state_store, _, _ = _make_helper()
        state_id = await self._setup_pending_state(state_store)
        with pytest.raises(OAuthStateError, match="redirect_uri mismatch"):
            await helper.complete("p", "conn-1", "code", state_id, "https://different.example/cb")

    async def test_expired_state_raises(self):
        helper, state_store, _, _ = _make_helper()
        pending = OAuthPendingState(
            connection_id="conn-1",
            provider="p",
            redirect_uri="https://r",
            expires_at=datetime(2000, 1, 1, tzinfo=timezone.utc),  # already expired
        )
        await state_store.save_state(
            "state-old", pending.model_dump(mode="json"), pending.expires_at
        )
        with pytest.raises(OAuthStateError, match="expired"):
            await helper.complete("p", "conn-1", "code", "state-old", "https://r")
