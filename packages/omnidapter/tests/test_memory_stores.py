"""
Tests for the real in-memory store implementations in omnidapter.stores.memory,
including their use as Omnidapter defaults.
"""
from datetime import datetime, timedelta, timezone

import pytest
from omnidapter import InMemoryCredentialStore, InMemoryOAuthStateStore, Omnidapter
from omnidapter.auth.models import OAuth2Credentials
from omnidapter.core.metadata import AuthKind
from omnidapter.stores.credentials import StoredCredential
from omnidapter.stores.memory import (
    InMemoryCredentialStore as MemoryCredentialStore,
)
from omnidapter.stores.memory import (
    InMemoryOAuthStateStore as MemoryOAuthStateStore,
)


@pytest.fixture
def credential_store():
    return MemoryCredentialStore()


@pytest.fixture
def oauth_state_store():
    return MemoryOAuthStateStore()


@pytest.fixture
def sample_credential():
    return StoredCredential(
        provider_key="google",
        auth_kind=AuthKind.OAUTH2,
        credentials=OAuth2Credentials(
            access_token="test-access-token",
            refresh_token="test-refresh-token",
        ),
        granted_scopes=["calendar"],
    )


class TestInMemoryCredentialStore:
    async def test_get_nonexistent_returns_none(self, credential_store):
        result = await credential_store.get_credentials("nonexistent")
        assert result is None

    async def test_save_and_get(self, credential_store, sample_credential):
        await credential_store.save_credentials("conn_1", sample_credential)
        result = await credential_store.get_credentials("conn_1")
        assert result is not None
        assert result.provider_key == "google"

    async def test_delete(self, credential_store, sample_credential):
        await credential_store.save_credentials("conn_1", sample_credential)
        await credential_store.delete_credentials("conn_1")
        assert await credential_store.get_credentials("conn_1") is None

    async def test_delete_nonexistent_is_safe(self, credential_store):
        await credential_store.delete_credentials("nonexistent")

    async def test_overwrite(self, credential_store, sample_credential):
        await credential_store.save_credentials("conn_1", sample_credential)
        new_cred = sample_credential.model_copy(
            update={"credentials": OAuth2Credentials(access_token="new-token")}
        )
        await credential_store.save_credentials("conn_1", new_cred)
        result = await credential_store.get_credentials("conn_1")
        assert isinstance(result.credentials, OAuth2Credentials)
        assert result.credentials.access_token == "new-token"

    async def test_multiple_connections_are_isolated(self, credential_store, sample_credential):
        cred_b = sample_credential.model_copy(
            update={"credentials": OAuth2Credentials(access_token="token-b")}
        )
        await credential_store.save_credentials("conn_a", sample_credential)
        await credential_store.save_credentials("conn_b", cred_b)

        result_a = await credential_store.get_credentials("conn_a")
        result_b = await credential_store.get_credentials("conn_b")
        assert result_a.credentials.access_token == "test-access-token"
        assert result_b.credentials.access_token == "token-b"

    def test_no_seed_method(self, credential_store):
        assert not hasattr(credential_store, "seed")


class TestInMemoryOAuthStateStore:
    async def test_save_and_load(self, oauth_state_store):
        expires = datetime.now(tz=timezone.utc) + timedelta(minutes=10)
        await oauth_state_store.save_state("state_1", {"foo": "bar"}, expires)
        result = await oauth_state_store.load_state("state_1")
        assert result == {"foo": "bar"}

    async def test_load_nonexistent_returns_none(self, oauth_state_store):
        assert await oauth_state_store.load_state("nonexistent") is None

    async def test_delete(self, oauth_state_store):
        expires = datetime.now(tz=timezone.utc) + timedelta(minutes=10)
        await oauth_state_store.save_state("state_1", {"foo": "bar"}, expires)
        await oauth_state_store.delete_state("state_1")
        assert await oauth_state_store.load_state("state_1") is None

    async def test_delete_nonexistent_is_safe(self, oauth_state_store):
        await oauth_state_store.delete_state("nonexistent")

    async def test_expired_state_returns_none(self, oauth_state_store):
        past = datetime.now(tz=timezone.utc) - timedelta(minutes=1)
        await oauth_state_store.save_state("state_expired", {"foo": "bar"}, past)
        assert await oauth_state_store.load_state("state_expired") is None

    async def test_expired_state_is_cleaned_up(self, oauth_state_store):
        past = datetime.now(tz=timezone.utc) - timedelta(minutes=1)
        await oauth_state_store.save_state("state_expired", {"x": 1}, past)
        await oauth_state_store.load_state("state_expired")
        # Underlying dicts should be cleared
        assert "state_expired" not in oauth_state_store._store
        assert "state_expired" not in oauth_state_store._expiry


class TestOmnidapterDefaults:
    def test_instantiates_without_stores(self):
        omni = Omnidapter()
        assert isinstance(omni._credential_store, MemoryCredentialStore)
        assert isinstance(omni._oauth_state_store, MemoryOAuthStateStore)

    def test_explicit_stores_are_used(self, sample_credential):
        store = MemoryCredentialStore()
        omni = Omnidapter(credential_store=store)
        assert omni._credential_store is store

    def test_top_level_exports(self):
        assert InMemoryCredentialStore is MemoryCredentialStore
        assert InMemoryOAuthStateStore is MemoryOAuthStateStore
