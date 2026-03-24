"""Unit tests for server provider registry assembly."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from omnidapter_server.config import Settings
from omnidapter_server.models.provider_config import ProviderConfig
from omnidapter_server.provider_registry import build_provider_registry


@pytest.fixture(autouse=True)
def clear_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in [
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "MICROSOFT_CLIENT_ID",
        "MICROSOFT_CLIENT_SECRET",
        "ZOHO_CLIENT_ID",
        "ZOHO_CLIENT_SECRET",
        "OMNIDAPTER_APPLE_ENABLED",
    ]:
        monkeypatch.delenv(key, raising=False)


def test_build_provider_registry_registers_fallback_credentials() -> None:
    settings = Settings(
        omnidapter_google_client_id="fallback-google-id",
        omnidapter_google_client_secret="fallback-google-secret",
    )

    registry = build_provider_registry(settings)
    oauth = registry.get("google").get_oauth_config()

    assert oauth is not None
    assert oauth.client_id == "fallback-google-id"
    assert oauth.client_secret == "fallback-google-secret"


def test_build_provider_registry_provider_config_overrides_fallback() -> None:
    settings = Settings(
        omnidapter_google_client_id="fallback-google-id",
        omnidapter_google_client_secret="fallback-google-secret",
    )
    provider_config = ProviderConfig(
        id=uuid.uuid4(),
        provider_key="google",
        auth_kind="oauth2",
        client_id_encrypted="enc-id",
        client_secret_encrypted="enc-secret",
        is_fallback=False,
    )
    encryption = MagicMock()
    encryption.decrypt.side_effect = ["db-google-id", "db-google-secret"]

    registry = build_provider_registry(
        settings,
        provider_config=provider_config,
        encryption=encryption,
    )
    oauth = registry.get("google").get_oauth_config()

    assert oauth is not None
    assert oauth.client_id == "db-google-id"
    assert oauth.client_secret == "db-google-secret"
    assert encryption.decrypt.call_count == 2


def test_build_provider_registry_requires_encryption_for_provider_override() -> None:
    settings = Settings()
    provider_config = ProviderConfig(
        id=uuid.uuid4(),
        provider_key="google",
        auth_kind="oauth2",
        client_id_encrypted="enc-id",
        client_secret_encrypted="enc-secret",
        is_fallback=False,
    )

    with pytest.raises(ValueError, match="Encryption service is required"):
        build_provider_registry(settings, provider_config=provider_config)


def test_build_provider_registry_validates_encrypted_credential_presence() -> None:
    settings = Settings()
    provider_config = ProviderConfig(
        id=uuid.uuid4(),
        provider_key="google",
        auth_kind="oauth2",
        client_id_encrypted=None,
        client_secret_encrypted=None,
        is_fallback=False,
    )

    with pytest.raises(ValueError, match="missing encrypted OAuth credentials"):
        build_provider_registry(
            settings,
            provider_config=provider_config,
            encryption=MagicMock(),
        )


def test_build_provider_registry_ignores_unknown_provider_key() -> None:
    settings = Settings()
    provider_config = ProviderConfig(
        id=uuid.uuid4(),
        provider_key="custom-provider",
        auth_kind="oauth2",
        client_id_encrypted="enc-id",
        client_secret_encrypted="enc-secret",
        is_fallback=False,
    )
    encryption = MagicMock()
    encryption.decrypt.side_effect = ["id", "secret"]

    registry = build_provider_registry(
        settings,
        provider_config=provider_config,
        encryption=encryption,
    )

    with pytest.raises(KeyError):
        registry.get("custom-provider")
