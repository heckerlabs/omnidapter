"""
Unit tests for omnidapter.auth.refresh.TokenRefreshManager.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from omnidapter.auth.models import ApiKeyCredentials, BasicCredentials, OAuth2Credentials
from omnidapter.auth.refresh import TokenRefreshManager
from omnidapter.core.errors import ConnectionNotFoundError
from omnidapter.core.metadata import AuthKind
from omnidapter.stores.credentials import StoredCredential
from omnidapter.testing.fakes.stores import InMemoryCredentialStore

# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _stored_oauth(
    expired: bool = False,
    refreshable: bool = True,
    provider_key: str = "test_provider",
) -> StoredCredential:
    expires_at = (
        datetime(2000, 1, 1, tzinfo=timezone.utc)
        if expired
        else datetime.now(tz=timezone.utc) + timedelta(hours=1)
    )
    return StoredCredential(
        provider_key=provider_key,
        auth_kind=AuthKind.OAUTH2,
        credentials=OAuth2Credentials(
            access_token="old-access",
            refresh_token="rt-123" if refreshable else None,
            expires_at=expires_at,
        ),
    )


def _stored_apikey(provider_key: str = "test_provider") -> StoredCredential:
    return StoredCredential(
        provider_key=provider_key,
        auth_kind=AuthKind.API_KEY,
        credentials=ApiKeyCredentials(api_key="key-abc"),
    )


def _stored_basic(provider_key: str = "test_provider") -> StoredCredential:
    return StoredCredential(
        provider_key=provider_key,
        auth_kind=AuthKind.BASIC,
        credentials=BasicCredentials(username="u", password="p"),
    )


def _make_manager(
    credential_store: InMemoryCredentialStore | None = None,
    *,
    retry_policy=None,
    http_client=None,
) -> tuple[TokenRefreshManager, InMemoryCredentialStore, MagicMock]:
    store = credential_store or InMemoryCredentialStore()
    registry = MagicMock()
    mgr = TokenRefreshManager(
        registry=registry,
        credential_store=store,
        retry_policy=retry_policy,
        http_client=http_client,
    )
    return mgr, store, registry


# --------------------------------------------------------------------------- #
# ensure_fresh — missing connection                                            #
# --------------------------------------------------------------------------- #


class TestEnsureFreshMissing:
    async def test_raises_connection_not_found(self):
        mgr, _, _ = _make_manager()
        with pytest.raises(ConnectionNotFoundError):
            await mgr.ensure_fresh("nonexistent")


# --------------------------------------------------------------------------- #
# ensure_fresh — non-OAuth credentials                                        #
# --------------------------------------------------------------------------- #


class TestEnsureFreshNonOAuth:
    async def test_api_key_returned_unchanged(self):
        mgr, store, _ = _make_manager()
        stored = _stored_apikey()
        store.seed("conn-1", stored)
        result = await mgr.ensure_fresh("conn-1")
        assert result is stored

    async def test_basic_returned_unchanged(self):
        mgr, store, _ = _make_manager()
        stored = _stored_basic()
        store.seed("conn-1", stored)
        result = await mgr.ensure_fresh("conn-1")
        assert result is stored


# --------------------------------------------------------------------------- #
# ensure_fresh — OAuth2, token not expired                                    #
# --------------------------------------------------------------------------- #


class TestEnsureFreshNotExpired:
    async def test_fresh_token_returned_without_refresh(self):
        mgr, store, registry = _make_manager()
        stored = _stored_oauth(expired=False)
        store.seed("conn-1", stored)
        result = await mgr.ensure_fresh("conn-1")
        assert result is stored
        registry.get.assert_not_called()


# --------------------------------------------------------------------------- #
# ensure_fresh — OAuth2, expired but not refreshable                          #
# --------------------------------------------------------------------------- #


class TestEnsureFreshExpiredNoRefreshToken:
    async def test_expired_no_refresh_token_returned_as_is(self):
        mgr, store, registry = _make_manager()
        stored = _stored_oauth(expired=True, refreshable=False)
        store.seed("conn-1", stored)
        result = await mgr.ensure_fresh("conn-1")
        # Not refreshable — returned unchanged
        assert result is stored
        registry.get.assert_not_called()


# --------------------------------------------------------------------------- #
# ensure_fresh — OAuth2, expired and refreshable                              #
# --------------------------------------------------------------------------- #


class TestEnsureFreshRefreshes:
    async def test_token_refreshed_and_persisted(self):
        mgr, store, registry = _make_manager()
        old_stored = _stored_oauth(expired=True)
        store.seed("conn-1", old_stored)

        new_creds = OAuth2Credentials(
            access_token="new-access",
            refresh_token="new-rt",
            expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=1),
        )
        new_stored = StoredCredential(
            provider_key="test_provider",
            auth_kind=AuthKind.OAUTH2,
            credentials=new_creds,
        )
        mock_provider = MagicMock()
        mock_provider.refresh_token = AsyncMock(return_value=new_stored)
        registry.get.return_value = mock_provider

        result = await mgr.ensure_fresh("conn-1")
        assert result is new_stored
        # Persisted
        saved = await store.get_credentials("conn-1")
        assert saved is new_stored

    async def test_refresh_configures_provider_transport(self):
        from omnidapter.transport.retry import RetryPolicy

        retry_policy = RetryPolicy.no_retry()
        shared_client = MagicMock()
        mgr, store, registry = _make_manager(
            retry_policy=retry_policy,
            http_client=shared_client,
        )
        old_stored = _stored_oauth(expired=True)
        store.seed("conn-1", old_stored)

        new_stored = _stored_oauth(expired=False)
        mock_provider = MagicMock()
        mock_provider.refresh_token = AsyncMock(return_value=new_stored)
        registry.get.return_value = mock_provider

        await mgr.ensure_fresh("conn-1")

        mock_provider.configure_oauth_transport.assert_called_once_with(
            retry_policy=retry_policy,
            hooks=None,
            http_client=shared_client,
        )
