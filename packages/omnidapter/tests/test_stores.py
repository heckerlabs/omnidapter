"""
Unit tests for in-memory store implementations.
"""
from datetime import datetime, timedelta, timezone

import pytest
from omnidapter.auth.models import OAuth2Credentials
from omnidapter.core.metadata import AuthKind
from omnidapter.stores.credentials import StoredCredential
from omnidapter.testing.fakes.stores import InMemoryCredentialStore, InMemoryOAuthStateStore


@pytest.fixture
def credential_store():
    return InMemoryCredentialStore()


@pytest.fixture
def oauth_state_store():
    return InMemoryOAuthStateStore()


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
        result = await credential_store.get_credentials("conn_1")
        assert result is None

    async def test_delete_nonexistent_is_safe(self, credential_store):
        # Should not raise
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

    async def test_seed(self, credential_store, sample_credential):
        credential_store.seed("conn_seed", sample_credential)
        result = await credential_store.get_credentials("conn_seed")
        assert result is not None


class TestInMemoryOAuthStateStore:
    async def test_save_and_load(self, oauth_state_store):
        expires = datetime.now(tz=timezone.utc) + timedelta(minutes=10)
        await oauth_state_store.save_state("state_1", {"foo": "bar"}, expires)
        result = await oauth_state_store.load_state("state_1")
        assert result == {"foo": "bar"}

    async def test_load_nonexistent_returns_none(self, oauth_state_store):
        result = await oauth_state_store.load_state("nonexistent")
        assert result is None

    async def test_delete(self, oauth_state_store):
        expires = datetime.now(tz=timezone.utc) + timedelta(minutes=10)
        await oauth_state_store.save_state("state_1", {"foo": "bar"}, expires)
        await oauth_state_store.delete_state("state_1")
        result = await oauth_state_store.load_state("state_1")
        assert result is None

    async def test_expired_state_returns_none(self, oauth_state_store):
        past = datetime.now(tz=timezone.utc) - timedelta(minutes=1)
        await oauth_state_store.save_state("state_expired", {"foo": "bar"}, past)
        result = await oauth_state_store.load_state("state_expired")
        assert result is None
