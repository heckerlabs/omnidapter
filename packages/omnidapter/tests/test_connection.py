"""
Unit tests for omnidapter.core.connection.Connection and omnidapter.core.omnidapter.Omnidapter.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from omnidapter.auth.models import ApiKeyCredentials, OAuth2Credentials
from omnidapter.core.connection import Connection
from omnidapter.core.errors import ConnectionNotFoundError
from omnidapter.core.metadata import AuthKind
from omnidapter.core.omnidapter import Omnidapter
from omnidapter.core.registry import ProviderRegistry
from omnidapter.stores.credentials import StoredCredential
from omnidapter.testing.fakes.stores import InMemoryCredentialStore, InMemoryOAuthStateStore

# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

def _stored_apikey(provider_key: str = "google") -> StoredCredential:
    return StoredCredential(
        provider_key=provider_key,
        auth_kind=AuthKind.API_KEY,
        credentials=ApiKeyCredentials(api_key="key-abc"),
    )


def _stored_oauth(provider_key: str = "google", expired: bool = False) -> StoredCredential:
    expires_at = (
        datetime(2000, 1, 1, tzinfo=timezone.utc)
        if expired
        else datetime.now(tz=timezone.utc) + timedelta(hours=1)
    )
    return StoredCredential(
        provider_key=provider_key,
        auth_kind=AuthKind.OAUTH2,
        credentials=OAuth2Credentials(
            access_token="at",
            refresh_token="rt",
            expires_at=expires_at,
        ),
    )


def _mock_registry(provider_key: str = "google") -> MagicMock:
    from omnidapter.core.metadata import ServiceKind

    mock_service = MagicMock()
    mock_provider = MagicMock()
    mock_provider.get_calendar_service.return_value = mock_service
    mock_provider.metadata.services = {ServiceKind.CALENDAR}

    registry = MagicMock()
    registry.get.return_value = mock_provider
    return registry


# --------------------------------------------------------------------------- #
# Connection                                                                   #
# --------------------------------------------------------------------------- #

class TestConnection:
    def test_properties(self):
        stored = _stored_apikey("google")
        registry = _mock_registry()
        conn = Connection("conn-1", stored, registry)
        assert conn.connection_id == "conn-1"
        assert conn.provider_key == "google"
        assert conn.stored_credential is stored

    def test_calendar_calls_provider(self):
        stored = _stored_apikey("google")
        registry = _mock_registry()
        conn = Connection("conn-1", stored, registry)
        svc = conn.calendar()
        assert svc is not None
        registry.get.assert_called_with("google")
        registry.get.return_value.get_calendar_service.assert_called_once_with(
            connection_id="conn-1",
            stored_credential=stored,
            retry_policy=None,
            hooks=None,
        )

    def test_calendar_passes_retry_policy(self):
        from omnidapter.transport.retry import RetryPolicy
        stored = _stored_apikey()
        registry = _mock_registry()
        policy = RetryPolicy.no_retry()
        conn = Connection("conn-1", stored, registry, retry_policy=policy)
        conn.calendar()
        registry.get.return_value.get_calendar_service.assert_called_once_with(
            connection_id="conn-1",
            stored_credential=stored,
            retry_policy=policy,
            hooks=None,
        )


# --------------------------------------------------------------------------- #
# Omnidapter                                                                   #
# --------------------------------------------------------------------------- #

class TestOmnidapter:
    def _omni(self, **kwargs) -> tuple[Omnidapter, InMemoryCredentialStore, InMemoryOAuthStateStore]:
        cred_store = InMemoryCredentialStore()
        state_store = InMemoryOAuthStateStore()
        omni = Omnidapter(
            credential_store=cred_store,
            oauth_state_store=state_store,
            registry=ProviderRegistry(),
            **kwargs,
        )
        return omni, cred_store, state_store

    async def test_connection_raises_when_not_found(self):
        omni, _, _ = self._omni()
        with pytest.raises(ConnectionNotFoundError):
            await omni.connection("missing")

    async def test_connection_returns_connection_object(self):
        omni, cred_store, _ = self._omni(auto_refresh=False)
        stored = _stored_apikey("google")

        # Register a fake google provider
        mock_provider = MagicMock()
        mock_provider.metadata.provider_key = "google"
        omni.register_provider(mock_provider)

        cred_store.seed("conn-1", stored)
        conn = await omni.connection("conn-1")
        assert isinstance(conn, Connection)
        assert conn.connection_id == "conn-1"
        assert conn.provider_key == "google"

    async def test_connection_auto_refresh_fresh_token(self):
        omni, cred_store, _ = self._omni(auto_refresh=True)
        stored = _stored_oauth("google", expired=False)

        mock_provider = MagicMock()
        mock_provider.metadata.provider_key = "google"
        omni.register_provider(mock_provider)

        cred_store.seed("conn-1", stored)
        conn = await omni.connection("conn-1")
        assert conn.connection_id == "conn-1"

    async def test_register_provider_adds_to_registry(self):
        omni, _, _ = self._omni()
        mock_provider = MagicMock()
        mock_provider.metadata.provider_key = "custom"
        mock_provider.metadata.display_name = "Custom"
        omni.register_provider(mock_provider)
        assert "custom" in omni.list_providers()

    async def test_describe_provider(self):
        omni, _, _ = self._omni()
        mock_provider = MagicMock()
        mock_provider.metadata.provider_key = "custom"
        mock_provider.metadata.display_name = "Custom"
        omni.register_provider(mock_provider)
        meta = omni.describe_provider("custom")
        assert meta is mock_provider.metadata

    async def test_list_providers_empty_without_builtins(self):
        omni, _, _ = self._omni()
        assert omni.list_providers() == []

    async def test_list_providers_with_builtins(self):
        omni = Omnidapter()
        providers = omni.list_providers()
        assert "google" in providers
        assert "microsoft" in providers
        assert "caldav" in providers
        assert "zoho" in providers

    async def test_oauth_property_accessible(self):
        omni, _, _ = self._omni()
        assert omni.oauth is not None

    async def test_registry_property_accessible(self):
        omni, _, _ = self._omni()
        assert omni.registry is not None

    async def test_connection_no_auto_refresh_missing_raises(self):
        omni, _, _ = self._omni(auto_refresh=False)
        with pytest.raises(ConnectionNotFoundError):
            await omni.connection("nonexistent")
