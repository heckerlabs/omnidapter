"""Unit tests for OAuth provider configuration validation."""

from __future__ import annotations

import pytest
from omnidapter.core.errors import ProviderNotConfiguredError
from omnidapter.providers.google.provider import GoogleProvider


class TestOAuthProviderConfiguration:
    def test_google_provider_requires_client_id_and_secret(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
        monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)

        provider = GoogleProvider()
        with pytest.raises(ProviderNotConfiguredError) as exc:
            provider.get_oauth_config()

        assert exc.value.provider_key == "google"
        assert exc.value.missing_fields == ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"]

    def test_google_provider_reports_partial_missing(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
        monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)

        provider = GoogleProvider(client_id="gid")
        with pytest.raises(ProviderNotConfiguredError) as exc:
            provider.get_oauth_config()

        assert exc.value.missing_fields == ["GOOGLE_CLIENT_SECRET"]

    def test_google_provider_treats_blank_env_values_as_missing(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "  ")

        provider = GoogleProvider()
        with pytest.raises(ProviderNotConfiguredError) as exc:
            provider.get_oauth_config()

        assert exc.value.missing_fields == ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"]

    def test_google_provider_reads_credentials_from_env(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "gid")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "gsecret")

        provider = GoogleProvider()
        config = provider.get_oauth_config()

        assert config is not None
        assert config.client_id == "gid"
        assert config.client_secret == "gsecret"

    def test_google_provider_accepts_explicit_credentials(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
        monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)

        provider = GoogleProvider(client_id="gid", client_secret="gsecret")
        config = provider.get_oauth_config()

        assert config is not None
        assert config.client_id == "gid"
        assert config.client_secret == "gsecret"
