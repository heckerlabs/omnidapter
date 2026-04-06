"""
Unit tests for omnidapter.core.registry.ProviderRegistry.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest
from omnidapter.core.registry import ProviderRegistry

# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _mock_provider(key: str, display_name: str = "Test Provider") -> MagicMock:
    meta = MagicMock()
    meta.provider_key = key
    meta.display_name = display_name
    provider = MagicMock()
    provider.metadata = meta
    return provider


# --------------------------------------------------------------------------- #
# Tests                                                                        #
# --------------------------------------------------------------------------- #


class TestProviderRegistry:
    def test_register_and_get(self):
        reg = ProviderRegistry()
        provider = _mock_provider("google")
        reg.register(provider)
        assert reg.get("google") is provider

    def test_get_unknown_raises_key_error(self):
        reg = ProviderRegistry()
        with pytest.raises(KeyError, match="'unknown'"):
            reg.get("unknown")

    def test_list_keys_empty(self):
        reg = ProviderRegistry()
        assert reg.list_keys() == []

    def test_list_keys_after_registration(self):
        reg = ProviderRegistry()
        reg.register(_mock_provider("google"))
        reg.register(_mock_provider("microsoft"))
        keys = reg.list_keys()
        assert "google" in keys
        assert "microsoft" in keys
        assert len(keys) == 2

    def test_describe_returns_metadata(self):
        reg = ProviderRegistry()
        provider = _mock_provider("zoho")
        reg.register(provider)
        meta = reg.describe("zoho")
        assert meta is provider.metadata

    def test_describe_unknown_raises(self):
        reg = ProviderRegistry()
        with pytest.raises(KeyError):
            reg.describe("nope")

    def test_overwrite_existing_provider(self):
        reg = ProviderRegistry()
        p1 = _mock_provider("google", "Old")
        p2 = _mock_provider("google", "New")
        reg.register(p1)
        reg.register(p2)
        assert reg.get("google") is p2
        assert len(reg.list_keys()) == 1

    def test_register_builtins_registers_configured_providers(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "gid")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "gsecret")
        monkeypatch.setenv("MICROSOFT_CLIENT_ID", "mid")
        monkeypatch.setenv("MICROSOFT_CLIENT_SECRET", "msecret")
        monkeypatch.setenv("ZOHO_CLIENT_ID", "zid")
        monkeypatch.setenv("ZOHO_CLIENT_SECRET", "zsecret")
        monkeypatch.delenv("OMNIDAPTER_APPLE_ENABLED", raising=False)
        monkeypatch.delenv("OMNIDAPTER_CALDAV_ENABLED", raising=False)

        reg = ProviderRegistry()
        reg.register_builtins()
        keys = reg.list_keys()
        assert "google" in keys
        assert "microsoft" in keys
        assert "zoho" in keys
        assert "apple" not in keys
        assert "caldav" not in keys

    def test_register_builtins_registers_apple_when_enabled(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
        monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("MICROSOFT_CLIENT_ID", raising=False)
        monkeypatch.delenv("MICROSOFT_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("ZOHO_CLIENT_ID", raising=False)
        monkeypatch.delenv("ZOHO_CLIENT_SECRET", raising=False)
        monkeypatch.setenv("OMNIDAPTER_APPLE_ENABLED", "1")
        monkeypatch.delenv("OMNIDAPTER_CALDAV_ENABLED", raising=False)

        reg = ProviderRegistry()
        reg.register_builtins()
        keys = reg.list_keys()

        assert keys == ["apple"]

    def test_register_builtins_registers_caldav_when_enabled(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
        monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("MICROSOFT_CLIENT_ID", raising=False)
        monkeypatch.delenv("MICROSOFT_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("ZOHO_CLIENT_ID", raising=False)
        monkeypatch.delenv("ZOHO_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("OMNIDAPTER_APPLE_ENABLED", raising=False)
        monkeypatch.setenv("OMNIDAPTER_CALDAV_ENABLED", "1")

        reg = ProviderRegistry()
        reg.register_builtins()
        keys = reg.list_keys()

        assert keys == ["caldav"]

    def test_register_builtins_skips_unconfigured_oauth_providers(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
        monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("MICROSOFT_CLIENT_ID", raising=False)
        monkeypatch.delenv("MICROSOFT_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("ZOHO_CLIENT_ID", raising=False)
        monkeypatch.delenv("ZOHO_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("OMNIDAPTER_APPLE_ENABLED", raising=False)
        monkeypatch.delenv("OMNIDAPTER_CALDAV_ENABLED", raising=False)

        reg = ProviderRegistry()
        reg.register_builtins()
        keys = reg.list_keys()

        assert "apple" not in keys
        assert "caldav" not in keys
        assert "google" not in keys
        assert "microsoft" not in keys
        assert "zoho" not in keys
        assert keys == []

    def test_register_builtins_warns_when_none_available(self, monkeypatch, caplog):
        monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
        monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("MICROSOFT_CLIENT_ID", raising=False)
        monkeypatch.delenv("MICROSOFT_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("ZOHO_CLIENT_ID", raising=False)
        monkeypatch.delenv("ZOHO_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("OMNIDAPTER_APPLE_ENABLED", raising=False)
        monkeypatch.delenv("OMNIDAPTER_CALDAV_ENABLED", raising=False)

        reg = ProviderRegistry()
        with caplog.at_level(logging.WARNING, logger="omnidapter.registry"):
            reg.register_builtins()

        assert "No built-in providers were auto-registered" in caplog.text

    def test_register_builtins_warns_when_no_oauth_available(self, monkeypatch, caplog):
        monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
        monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("MICROSOFT_CLIENT_ID", raising=False)
        monkeypatch.delenv("MICROSOFT_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("ZOHO_CLIENT_ID", raising=False)
        monkeypatch.delenv("ZOHO_CLIENT_SECRET", raising=False)
        monkeypatch.setenv("OMNIDAPTER_APPLE_ENABLED", "true")
        monkeypatch.delenv("OMNIDAPTER_CALDAV_ENABLED", raising=False)

        reg = ProviderRegistry()
        with caplog.at_level(logging.WARNING, logger="omnidapter.registry"):
            reg.register_builtins()

        assert "No OAuth providers were auto-registered" in caplog.text

    def test_register_builtins_registers_all_when_auto_register_disabled(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
        monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("MICROSOFT_CLIENT_ID", raising=False)
        monkeypatch.delenv("MICROSOFT_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("ZOHO_CLIENT_ID", raising=False)
        monkeypatch.delenv("ZOHO_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("OMNIDAPTER_APPLE_ENABLED", raising=False)
        monkeypatch.delenv("OMNIDAPTER_CALDAV_ENABLED", raising=False)

        reg = ProviderRegistry()
        reg.register_builtins(auto_register_by_env=False)
        keys = reg.list_keys()

        assert "google" in keys
        assert "microsoft" in keys
        assert "zoho" in keys
        assert "apple" in keys
        assert "caldav" in keys

    def test_register_builtins_providers_have_metadata(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "gid")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "gsecret")
        monkeypatch.setenv("MICROSOFT_CLIENT_ID", "mid")
        monkeypatch.setenv("MICROSOFT_CLIENT_SECRET", "msecret")
        monkeypatch.setenv("ZOHO_CLIENT_ID", "zid")
        monkeypatch.setenv("ZOHO_CLIENT_SECRET", "zsecret")
        monkeypatch.delenv("OMNIDAPTER_APPLE_ENABLED", raising=False)
        monkeypatch.delenv("OMNIDAPTER_CALDAV_ENABLED", raising=False)

        reg = ProviderRegistry()
        reg.register_builtins()
        for key in reg.list_keys():
            meta = reg.describe(key)
            assert meta.provider_key == key
            assert meta.display_name
